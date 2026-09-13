import { redirect } from "next/navigation";
import { executionIdPattern } from "@/lib/execution-details";

/** Compatibility for saved links; there is no standalone task workspace. */
export default async function RetiredTasksPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ locale }, search] = await Promise.all([params, searchParams]);
  const query = new URLSearchParams();
  if (typeof search.id === "string" && executionIdPattern.test(search.id))
    query.set("run", search.id);
  if (
    typeof search.project === "string" &&
    (search.project === "default" || executionIdPattern.test(search.project))
  )
    query.set("project", search.project);
  const prefix = ["en", "pl"].includes(locale) ? `/${locale}` : "";
  redirect(`${prefix}/chat${query.size ? `?${query}` : ""}`);
}
