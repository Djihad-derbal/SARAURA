import { Suspense } from "react";
import { LandingLoader } from "@/components/Loaders";

export default function Page() {
  return (
    <Suspense>
      <LandingLoader />
    </Suspense>
  );
}
