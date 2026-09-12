/**
 * Hardcoded teaser plans used as a fallback when the Stripe-driven
 * `/billing/plans` endpoint returns an empty list — so the marketing surface
 * stays consistent regardless of backend state.
 *
 * Shape mirrors the simplified one used by `<PricingTeaser />` on the landing
 * page. The full /pricing page maps these into its own card UI.
 *
 * Replace these copy strings via the i18n `marketing.pricing.plans.*` keys
 * once you localize for additional languages.
 */
import { ROUTES } from "@/lib/constants";

export interface TeaserPlan {
  name: string;
  /** Display price, currency-prefixed (e.g. "$0", "$29"). Leave empty for "Custom". */
  price: string;
  /** Cadence label shown next to price (e.g. "/ month", "/ user / month"). */
  cadence?: string;
  description: string;
  features: string[];
  cta: { label: string; href: string };
  featured?: boolean;
  badge?: string;
}

export const TEASER_PLANS: TeaserPlan[] = [
  {
    name: "Starter",
    price: "$0",
    cadence: "/ month",
    description: "For individuals exploring the product.",
    features: ["100 messages / day", "1 connected data source", "Community support"],
    cta: { label: "Start free", href: ROUTES.REGISTER },
  },
  {
    name: "Pro",
    price: "$29",
    cadence: "/ user / month",
    description: "For small teams getting real work done.",
    features: [
      "Unlimited messages",
      "10 connected sources",
      "Email + chat support",
      "Workflow automations",
    ],
    cta: { label: "Start 14-day trial", href: ROUTES.REGISTER },
    featured: true,
    badge: "Most popular",
  },
  {
    name: "Business",
    price: "$99",
    cadence: "/ user / month",
    description: "For organisations rolling out across teams.",
    features: [
      "Everything in Pro",
      "SSO + audit log",
      "Role-based access control",
      "Dedicated success manager",
    ],
    cta: { label: "Talk to sales", href: ROUTES.CONTACT },
  },
];

/** Polish translations of the same plans. Returned by helpers when locale=pl. */
export const TEASER_PLANS_PL: TeaserPlan[] = [
  {
    name: "Starter",
    price: "0 zł",
    cadence: "/ miesiąc",
    description: "Dla osób eksplorujących produkt.",
    features: ["100 wiadomości / dzień", "1 podpięte źródło danych", "Wsparcie społeczności"],
    cta: { label: "Zacznij za darmo", href: ROUTES.REGISTER },
  },
  {
    name: "Pro",
    price: "129 zł",
    cadence: "/ user / miesiąc",
    description: "Dla małych zespołów robiących prawdziwą robotę.",
    features: [
      "Bez limitu wiadomości",
      "10 podpiętych źródeł",
      "Wsparcie email + czat",
      "Automatyzacje workflow",
    ],
    cta: { label: "Zacznij 14-dniowy trial", href: ROUTES.REGISTER },
    featured: true,
    badge: "Najpopularniejszy",
  },
  {
    name: "Business",
    price: "399 zł",
    cadence: "/ user / miesiąc",
    description: "Dla organizacji wdrażających rozwiązanie szeroko.",
    features: [
      "Wszystko z Pro",
      "SSO + audit log",
      "Role-based access control",
      "Dedykowany success manager",
    ],
    cta: { label: "Pogadaj ze sprzedażą", href: ROUTES.CONTACT },
  },
];

/** Simplified Chinese translations of the fallback plans. */
export const TEASER_PLANS_ZH: TeaserPlan[] = [
  {
    name: "入门版",
    price: "$0",
    cadence: "/月",
    description: "适合个人体验产品。",
    features: ["每天 100 条消息", "连接 1 个数据源", "社区支持"],
    cta: { label: "免费开始", href: ROUTES.REGISTER },
  },
  {
    name: "专业版",
    price: "$29",
    cadence: "/用户/月",
    description: "适合希望高效开展实际工作的中小团队。",
    features: ["消息数量不限", "连接 10 个数据源", "邮件与在线支持", "工作流自动化"],
    cta: { label: "开始 14 天试用", href: ROUTES.REGISTER },
    featured: true,
    badge: "最受欢迎",
  },
  {
    name: "企业版",
    price: "$99",
    cadence: "/用户/月",
    description: "适合在多个团队中全面部署的组织。",
    features: ["包含专业版全部功能", "SSO 与审计日志", "基于角色的访问控制", "专属客户成功经理"],
    cta: { label: "联系销售", href: ROUTES.CONTACT },
  },
];

export function getTeaserPlans(locale: string): TeaserPlan[] {
  if (locale === "pl") return TEASER_PLANS_PL;
  if (locale === "zh") return TEASER_PLANS_ZH;
  return TEASER_PLANS;
}
