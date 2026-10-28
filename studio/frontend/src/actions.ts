import { createContext, useContext } from "react";
import type { Report } from "./api";

/** The bot-wide actions of the top bar, for pages that lead into them (save, then validate, then publish). */
export interface BotActions { validate: () => Promise<Report | null>; openPublish: () => void; validating: boolean }
export const BotActionsContext = createContext<BotActions>({ validate: async () => null, openPublish: () => {}, validating: false });
export const useBotActions = () => useContext(BotActionsContext);
