import type { Metadata } from "next";
import { Suspense } from "react";
import { HomeLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Research explorer · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <HomeLoader />
    </Suspense>
  );
}
