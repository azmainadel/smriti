"use client";

import { useParams, useRouter } from "next/navigation";
import { ItemView } from "@/components/ItemView";

/** Direct links to an item get the same full-screen view; closing goes to the library. */
export default function ItemPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  return <ItemView id={id} onClose={() => router.push("/")} onOpenItem={(next) => router.replace(`/item/${next}`)} />;
}
