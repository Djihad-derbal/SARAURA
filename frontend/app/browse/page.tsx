import type { Metadata } from "next";
import { Suspense } from "react";
import { BrowseLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Raw Granules · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <BrowseLoader />
    </Suspense>
  );
}
