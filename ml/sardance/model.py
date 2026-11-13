"""ChangeUTAE: a compact U-Net with a temporal attention encoder for radar time series.

Input  x     (B, T, C, H, W)  normalised backscatter per pass (C = 2: HH, HV)
       days  (B, T)           days since the first pass
Output logits (B, K, H, W)    one score per change class

Each pass goes through the same 2-D encoder. At the coarsest scale an attention
layer decides, per location, which passes matter; the same weights then merge
the finer-scale features of every pass, so the decoder sees one feature map per
scale. Follows the U-TAE design (Garnot and Landrieu, 2021), reduced to about
half a million parameters so it trains on a 6 GB GPU.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F


def block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1), nn.GroupNorm(8, cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1), nn.GroupNorm(8, cout), nn.ReLU(inplace=True),
    )


class TemporalAttention(nn.Module):
    """Per-location attention over passes with a learned query per head."""

    def __init__(self, channels: int, heads: int = 4, d_key: int = 8):
        super().__init__()
        assert channels % heads == 0
        self.heads, self.d_key = heads, d_key
        self.key = nn.Conv2d(channels, heads * d_key, 1)
        self.query = nn.Parameter(torch.randn(heads, d_key) * 0.5)
        freqs = torch.exp(torch.arange(0, channels, 2).float() * (-math.log(1000.0) / channels))
        self.register_buffer("freqs", freqs)

    def positions(self, days: torch.Tensor) -> torch.Tensor:
        """Sinusoidal encoding of acquisition day, shape (B, T, C)."""
        a = days.unsqueeze(-1) * self.freqs
        return torch.stack([a.sin(), a.cos()], dim=-1).flatten(-2)

    def forward(self, x: torch.Tensor, days: torch.Tensor):
        b, t, c, h, w = x.shape
        x = x + self.positions(days)[:, :, :c, None, None]
        k = self.key(x.reshape(b * t, c, h, w)).reshape(b, t, self.heads, self.d_key, h, w)
        score = (k * self.query[None, None, :, :, None, None]).sum(3) / math.sqrt(self.d_key)
        attn = score.softmax(dim=1)  # (B, T, heads, h, w), sums to 1 over passes
        pooled = (x.reshape(b, t, self.heads, c // self.heads, h, w) * attn.unsqueeze(3)).sum(1)
        return pooled.reshape(b, c, h, w), attn


class ChangeUTAE(nn.Module):
    def __init__(self, in_channels: int = 2, n_classes: int = 6, widths=(32, 64, 128), heads: int = 4):
        super().__init__()
        self.enc = nn.ModuleList()
        cin = in_channels
        for wd in widths:
            self.enc.append(block(cin, wd))
            cin = wd
        self.attention = TemporalAttention(widths[-1], heads)
        self.dec = nn.ModuleList()
        for wd in reversed(widths[:-1]):
            self.dec.append(block(cin + wd, wd))
            cin = wd
        self.head = nn.Conv2d(cin, n_classes, 1)

    def forward(self, x: torch.Tensor, days: torch.Tensor, return_attention: bool = False):
        b, t, c, h, w = x.shape
        f = x.reshape(b * t, c, h, w)
        skips = []
        for i, enc in enumerate(self.enc):
            if i:
                f = F.max_pool2d(f, 2)
            f = enc(f)
            skips.append(f.reshape(b, t, f.shape[1], f.shape[2], f.shape[3]))
        out, attn = self.attention(skips[-1], days)
        weights = attn.mean(2)  # average heads -> (B, T, h, w)
        for dec, skip in zip(self.dec, reversed(skips[:-1])):
            size = skip.shape[-2:]
            wgt = F.interpolate(weights, size=size, mode="bilinear", align_corners=False)
            wgt = wgt / wgt.sum(1, keepdim=True).clamp_min(1e-6)
            merged = (skip * wgt.unsqueeze(2)).sum(1)
            out = dec(torch.cat([F.interpolate(out, size=size, mode="bilinear", align_corners=False), merged], dim=1))
        logits = self.head(out)
        return (logits, weights) if return_attention else logits


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
