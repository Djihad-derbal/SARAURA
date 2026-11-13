import type { Metadata } from "next";
import { Suspense } from "react";
import { ReportLoader } from "@/components/Loaders";

export const metadata: Metadata = { title: "Report · SARAURA" };

export default function Page() {
  return (
    <Suspense>
      <ReportLoader />
    </Suspense>
  );
}
