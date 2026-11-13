import type { Metadata } from "next";
import { Suspense } from "react";
import { ModelsLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Models · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <ModelsLoader />
    </Suspense>
  );
}
