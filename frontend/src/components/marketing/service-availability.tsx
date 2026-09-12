"use client";
import Link from "next/link";
import { useLocale } from "next-intl";
import { ROUTES } from "@/lib/constants";
export function ServiceAvailability() {
  const isZh = useLocale() === "zh";
  return (
    <div className="space-y-5 rounded-3xl border p-8">
      <h3 className="text-2xl font-semibold">
        {isZh ? "当前开放：AI 对话与私有知识库" : "Available: AI chat and private knowledge"}
      </h3>
      <p>
        {isZh
          ? "付费套餐尚未开放。私有知识库检索已开放；云盘同步和团队邀请暂不可用。"
          : "Paid plans are not available. Knowledge retrieval is available; cloud storage sync and team invitations are not enabled."}
      </p>
      <Link className="inline-flex rounded-full border px-5 py-3" href={ROUTES.PRICING}>
        {isZh ? "查看服务说明" : "View service availability"}
      </Link>
    </div>
  );
}
