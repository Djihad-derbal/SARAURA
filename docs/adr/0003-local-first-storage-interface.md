# Local-first, behind a storage interface

"Done" means a feature runs from a clean clone in local mode on real NISAR data; hosting comes later. Analysis results, tiles and the cache sit behind a storage interface (local disk now, object storage such as S3 later), and the Analysis area cap is a config value measured in seconds per km² per product. That way moving the workers next to the data in AWS us-west-2 means changing config, not rewriting the code.
