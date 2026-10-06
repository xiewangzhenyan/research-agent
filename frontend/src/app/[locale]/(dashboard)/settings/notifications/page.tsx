import { redirect } from "next/navigation";

import { ROUTES } from "@/lib/constants";

// The notification switches only lived in this browser and nothing ever sent the
// messages, so the page was retired. Old links continue at account settings.
export default function RetiredNotificationSettings() {
  redirect(ROUTES.SETTINGS_ACCOUNT);
}
