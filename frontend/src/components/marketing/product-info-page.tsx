import Link from "next/link";
import { getLocale } from "next-intl/server";
import { MarketingPageLayout } from "./marketing-page-layout";
import { ROUTES } from "@/lib/constants";

const copy = {
  zh: {
    cookies: [
      "Cookie 与本地存储说明",
      "本站使用 Cookie 保存登录状态和语言偏好。",
      "浏览器本地存储用于主题、引导进度和界面偏好。清除这些数据可能需要重新登录并重新设置偏好。",
      "发送消息时，对话上下文及本次附件的可解析内容会经服务器发送给管理员配置的模型服务。",
    ],
    help: [
      "使用帮助",
      "当前支持账号登录、AI 对话、私有知识库、原文引用、聊天附件与对话历史。",
      "在聊天输入框添加文件，然后发送问题，助手会使用本次附带的可解析内容。附件不会自动建立可跨对话检索的知识库。",
      "聊天框会显示当前默认模型。可在模型菜单中切换；默认模型由站点管理员统一配置。",
    ],
    rag: [
      "专属知识库已开放",
      "支持本地文档解析、分块、中文向量与混合检索。",
      "你可以先在聊天中上传附件并提问。聊天附件只用于对话，不代表文件已经加入知识库。",
      "从导航进入知识库上传文件，在聊天中选择知识库提问。云盘同步暂未开放。",
    ],
    pricing: [
      "服务与套餐",
      "当前站点尚未开放付费套餐、订阅和在线支付。",
      "请登录使用已开放的聊天功能。可用模型由管理员配置，本站暂未发布付费额度或服务承诺。",
      "私有知识库已开放；团队邀请和云盘同步暂不可用。",
    ],
    contact: [
      "联系与反馈",
      "遇到问题时，请通过你现有的联系渠道向站点管理员反馈。",
      "请提供发生问题的页面地址、操作步骤和时间；模型问题请附上模型名称和错误提示。",
      "本站尚未设置公开客服邮箱、销售预约或在线工单入口。请勿在反馈中提供密码或 API Key。",
    ],
    changelog: [
      "更新日志",
      "2026-09-09：知识库与宇宙工作区升级。",
      "新增本地中文向量与混合检索、真实文件处理状态、失败重试、分块预览和原文引用。知识数据按账号隔离。",
      "全新深色宇宙与薄荷绿界面，动态轨道首页、半透明知识工作区和安静的阅读区域，兼顾手机和减少动态效果设置。",
    ],
  },
  en: {
    cookies: [
      "Cookies and local storage",
      "This site uses cookies for sign-in and language preferences.",
      "Local storage keeps theme, onboarding progress, and interface preferences. Clearing it may require signing in and setting preferences again.",
      "When you send a message, the server forwards conversation context and readable attachment contents to the model service configured by the administrator.",
    ],
    help: [
      "Help",
      "This deployment supports sign-in, AI chat, chat attachments, conversation history, and profile settings.",
      "Attach a file in chat and send a question to use its readable contents. Attachments do not create a searchable knowledge base across conversations.",
      "The chat controls show the default model and let you select another configured model. The site administrator configures the default.",
    ],
    rag: [
      "Private knowledge bases are available",
      "Local document parsing, Chinese embeddings and hybrid retrieval are available.",
      "You can attach files to a chat and ask questions about them. Chat attachments are not knowledge base documents.",
      "Open Knowledge to upload documents, then select your knowledge bases in chat. Cloud sync is not enabled.",
    ],
    pricing: [
      "Service availability",
      "Paid plans, subscriptions, and online payments are not available on this site.",
      "Sign in to use chat. The administrator configures available models; no paid quotas or service commitments have been published.",
      "Private knowledge bases are available. Team invitations and cloud storage sync are not enabled.",
    ],
    contact: [
      "Contact and feedback",
      "Contact the site administrator through your existing contact channel.",
      "Include the page URL, steps to reproduce, and time of the issue. For model issues, include the model name and error message.",
      "No public support email, sales booking, or ticket form is configured. Do not include passwords or API keys in feedback.",
    ],
    changelog: [
      "Changelog",
      "2026-09-09: Native knowledge and cosmic workspace.",
      "Added local Chinese embeddings, hybrid retrieval, processing stages, retries, chunk previews and source citations, isolated by account.",
      "A dark cosmic interface with mint accents, responsive orbital motion and reduced-motion support.",
    ],
  },
};
export type ProductInfoKind = keyof typeof copy.zh;
export async function ProductInfoPage({ kind }: { kind: ProductInfoKind }) {
  const locale = await getLocale();
  const isZh = locale === "zh";
  const [title, description, ...paragraphs] = (isZh ? copy.zh : copy.en)[kind];
  const prefix = locale === "zh" ? "" : `/${locale}`;
  return (
    <MarketingPageLayout title={title!} description={description} width="narrow">
      <div className="space-y-6 text-base leading-relaxed">
        {paragraphs.map((text) => (
          <p key={text}>{text}</p>
        ))}
        <div className="flex flex-wrap gap-4 pt-4">
          <Link
            className="bg-foreground text-background rounded-full px-6 py-3"
            href={`${prefix}${ROUTES.CHAT}`}
          >
            {isZh ? "打开聊天" : "Open chat"}
          </Link>
          <Link className="rounded-full border px-6 py-3" href={`${prefix}${ROUTES.HELP}`}>
            {isZh ? "使用帮助" : "Help"}
          </Link>
        </div>
      </div>
    </MarketingPageLayout>
  );
}
