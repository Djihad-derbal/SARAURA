import type { Metadata } from "next";
import { Suspense } from "react";
import { PlaceLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Ask this place · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <PlaceLoader />
    </Suspense>
  );
}
