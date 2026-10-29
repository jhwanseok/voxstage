/** Every in-app address, always absolute. Links and redirects use these and never a relative `to`: inside a splat
 *  route ("*") React Router v7 resolves a relative path against the whole URL, so `to="home"` stacked segments
 *  (/mock/api/home/home/...). `src/routes.test.tsx` holds the regression test. */
export type BotSection = "overview" | "faq" | "flows" | "data" | "tools" | "validation" | "history";

export const paths = {
  home: () => "/",
  bot: (slug: string, section: BotSection = "overview") => `/b/${encodeURIComponent(slug)}/${section}`,
  flow: (slug: string, flowId: string) => `/b/${encodeURIComponent(slug)}/flows/${encodeURIComponent(flowId)}`,
  mock: (page: "home" | "faq" | "flow" = "home") => `/mock/${page}`,
};
