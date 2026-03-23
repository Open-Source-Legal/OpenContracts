/**
 * Tests for social media crawler detection utilities
 */

import { describe, it, expect } from "vitest";
import { isSocialMediaCrawler, isKnownBot, getCrawlerName } from "./crawler";

describe("isSocialMediaCrawler", () => {
  it("detects Twitter bot", () => {
    expect(isSocialMediaCrawler("Twitterbot/1.0")).toBe(true);
  });

  it("detects Facebook bot", () => {
    expect(
      isSocialMediaCrawler(
        "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
      )
    ).toBe(true);
  });

  it("detects LinkedIn bot", () => {
    expect(isSocialMediaCrawler("LinkedInBot/1.0")).toBe(true);
  });

  it("detects Slack bot", () => {
    expect(
      isSocialMediaCrawler("Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)")
    ).toBe(true);
  });

  it("detects Discord bot", () => {
    expect(isSocialMediaCrawler("Mozilla/5.0 (compatible; Discordbot/2.0)")).toBe(true);
  });

  it("detects WhatsApp bot", () => {
    expect(isSocialMediaCrawler("WhatsApp/2.21.5.17")).toBe(true);
  });

  it("detects Telegram bot", () => {
    expect(isSocialMediaCrawler("TelegramBot")).toBe(true);
  });

  it("detects Pinterest bot", () => {
    expect(isSocialMediaCrawler("Pinterest/0.2")).toBe(true);
  });

  it("detects Apple bot", () => {
    expect(isSocialMediaCrawler("Applebot/0.1")).toBe(true);
  });

  it("detects Reddit bot", () => {
    expect(isSocialMediaCrawler("Redditbot/1.0")).toBe(true);
  });

  it("detects Googlebot", () => {
    expect(isSocialMediaCrawler("Mozilla/5.0 (compatible; Googlebot/2.1)")).toBe(true);
  });

  it("detects Bingbot", () => {
    expect(isSocialMediaCrawler("Mozilla/5.0 (compatible; bingbot/2.0)")).toBe(true);
  });

  it("detects DuckDuckBot", () => {
    expect(isSocialMediaCrawler("DuckDuckBot/1.1")).toBe(true);
  });

  it("rejects regular browser user agents", () => {
    expect(
      isSocialMediaCrawler(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      )
    ).toBe(false);
  });

  it("rejects curl user agents", () => {
    expect(isSocialMediaCrawler("curl/7.68.0")).toBe(false);
  });

  it("handles empty user agent", () => {
    expect(isSocialMediaCrawler("")).toBe(false);
  });

  it("is case insensitive", () => {
    expect(isSocialMediaCrawler("TWITTERBOT")).toBe(true);
    expect(isSocialMediaCrawler("TwitterBot")).toBe(true);
    expect(isSocialMediaCrawler("twitterbot")).toBe(true);
  });
});

describe("isKnownBot", () => {
  it("detects user agents with 'bot'", () => {
    expect(isKnownBot("SomeRandomBot/1.0")).toBe(true);
  });

  it("detects user agents with 'crawler'", () => {
    expect(isKnownBot("MyCrawler/1.0")).toBe(true);
  });

  it("detects user agents with 'spider'", () => {
    expect(isKnownBot("SearchSpider/1.0")).toBe(true);
  });

  it("detects user agents with 'preview'", () => {
    expect(isKnownBot("LinkPreview/1.0")).toBe(true);
  });

  it("detects user agents with 'fetch'", () => {
    expect(isKnownBot("URLFetcher/1.0")).toBe(true);
  });

  it("rejects regular browsers", () => {
    expect(
      isKnownBot("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124")
    ).toBe(false);
  });
});

describe("getCrawlerName", () => {
  it("identifies Twitter", () => {
    expect(getCrawlerName("Twitterbot/1.0")).toBe("Twitter");
  });

  it("identifies Facebook", () => {
    expect(getCrawlerName("facebookexternalhit/1.1")).toBe("Facebook");
  });

  it("identifies LinkedIn", () => {
    expect(getCrawlerName("LinkedInBot/1.0")).toBe("LinkedIn");
  });

  it("identifies Slack", () => {
    expect(getCrawlerName("Slackbot-LinkExpanding")).toBe("Slack");
  });

  it("identifies Discord", () => {
    expect(getCrawlerName("Discordbot/2.0")).toBe("Discord");
  });

  it("identifies WhatsApp", () => {
    expect(getCrawlerName("WhatsApp/2.21")).toBe("WhatsApp");
  });

  it("identifies Telegram", () => {
    expect(getCrawlerName("TelegramBot")).toBe("Telegram");
  });

  it("identifies Pinterest", () => {
    expect(getCrawlerName("Pinterest/0.2")).toBe("Pinterest");
  });

  it("identifies Apple", () => {
    expect(getCrawlerName("Applebot/0.1")).toBe("Apple");
  });

  it("identifies Reddit", () => {
    expect(getCrawlerName("Redditbot/1.0")).toBe("Reddit");
  });

  it("identifies Google", () => {
    expect(getCrawlerName("Googlebot/2.1")).toBe("Google");
  });

  it("identifies Bing", () => {
    expect(getCrawlerName("Bingbot/2.0")).toBe("Bing");
  });

  it("returns Unknown Bot for generic bots", () => {
    expect(getCrawlerName("SomeRandomBot/1.0")).toBe("Unknown Bot");
  });

  it("returns null for regular browsers", () => {
    expect(
      getCrawlerName("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0")
    ).toBe(null);
  });
});
