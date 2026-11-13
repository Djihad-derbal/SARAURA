import type { Metadata } from "next";
import { Suspense } from "react";
import { StudyLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Study · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <StudyLoader />
    </Suspense>
  );
}
