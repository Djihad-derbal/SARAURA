import { Suspense } from "react";
import { HomeLoader } from "@/components/Loaders";

export default function Page() {
  return (
    <Suspense>
      <HomeLoader />
    </Suspense>
  );
}
