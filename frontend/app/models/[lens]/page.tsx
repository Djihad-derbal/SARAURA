import type { Metadata } from "next";
import { Suspense } from "react";
import { CardLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Model card · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <CardLoader />
    </Suspense>
  );
}
