import type { MetadataRoute } from "next";

/**
 * Keep crawlers out.
 *
 * This is a personal, non-commercial project built on data other people
 * publish. Several of those sources allow free use and ask that it not be
 * redistributed, which is exactly what an indexed public site does. Blocking
 * crawlers keeps "personal use" true rather than aspirational.
 *
 * It also stops a real cost: every crawl hits a server-rendered page, every
 * page queries Postgres, and that read is metered against a monthly transfer
 * allowance the app has already exceeded once.
 *
 * robots.txt asks politely and a determined crawler ignores it, so the layout
 * also sends `noindex`.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", disallow: "/" }],
  };
}
