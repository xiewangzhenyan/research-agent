import Link from "next/link";
import { Database, ArrowUpRight, ShieldCheck } from "lucide-react";
export default function Page() {
  return (
    <main id="main" className="cosmic-landing min-h-dvh px-6 py-20">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="text-brand text-sm">
          ← LSPR AI
        </Link>
        <Database className="text-brand mt-16 mb-6 h-10 w-10" />
        <h1 className="text-4xl font-semibold">你的专属知识空间</h1>
        <p className="mt-6 text-lg leading-8 text-slate-400">
          上传 PDF、Word、TXT、Markdown 或 CSV，查看真实处理状态，在对话中检索资料并展开原文引用。
        </p>
        <div className="cosmic-feature my-10 rounded-2xl p-7">
          <h2 className="mb-4 text-xl">资料就绪后，就能开始提问。</h2>
          <p className="text-sm leading-7 text-slate-400">
            支持多文件上传、重复文件去重、失败重试、分块预览与混合检索。单文件不超过 10 MB；扫描 PDF
            请先完成 OCR。
          </p>
          <p className="text-brand mt-5 text-sm">
            <ShieldCheck className="mr-2 inline h-4 w-4" />
            知识库、文件及检索结果按账号隔离
          </p>
        </div>
        <Link
          href="/knowledge"
          className="mint-action inline-flex items-center gap-4 rounded-full px-6 py-4"
        >
          进入知识库
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      </div>
    </main>
  );
}
