"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";

const blank = () => <div className="h-dvh w-full bg-bg" aria-busy="true" />;

// Maps and 3D need WebGL and the window object, so these render in the browser only.
const HomeView = dynamic(() => import("./home/Home"), { ssr: false, loading: blank });
const StudyView = dynamic(() => import("./study/StudyPage"), { ssr: false, loading: blank });
const BrowseView = dynamic(() => import("./Explorer"), { ssr: false, loading: blank });
const ReportView = dynamic(() => import("./report/Report"), { ssr: false, loading: () => <p className="p-8">Loading…</p> });
const ModelsView = dynamic(() => import("./models/Models").then((m) => m.ModelsTable), { ssr: false, loading: blank });
const CardView = dynamic(() => import("./models/Models").then((m) => m.ModelCardView), { ssr: false, loading: blank });

export const HomeLoader = () => <HomeView />;
export const BrowseLoader = () => <BrowseView />;
export const ModelsLoader = () => <ModelsView />;

export function StudyLoader() {
  const { id } = useParams<{ id: string }>();
  return <StudyView key={id} id={id} />;
}

export function ReportLoader() {
  const { id } = useParams<{ id: string }>();
  return <ReportView id={id} />;
}

export function CardLoader() {
  const { lens } = useParams<{ lens: string }>();
  return <CardView lens={lens} />;
}
