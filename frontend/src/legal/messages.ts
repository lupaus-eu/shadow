import type { Locale } from "../i18n";

type Copy = {
  footerLink: string;
  indexTitle: string;
  indexIntro: string;
  indexEmpty: string;
  version: (version: number, date: string) => string;
  draftBanner: string;
  notFound: string;
  failed: string;
  loading: string;
  back: string;
  language: string;
  languageNames: Record<Locale, string>;
  acceptance: { required: string; notice: string; none: string };
  signup: { heading: string; accept: (title: string) => string; read: string; failed: string };
  owner: {
    title: string;
    description: string;
    version: (version: number) => string;
    accepted: (version: number, when: string, who: string) => string;
    formerMember: string;
    notAccepted: string;
    due: string;
    accept: string;
    accepting: string;
    open: string;
    failed: string;
    banner: (titles: string) => string;
    bannerAction: string;
  };
};

const en: Copy = {
  footerLink: "Terms and privacy",
  indexTitle: "Terms, privacy, and security",
  indexIntro: "The documents that govern the Yearclock service.",
  indexEmpty: "No documents are published yet.",
  version: (version, date) => `Version ${version}, in force from ${date}`,
  draftBanner: "Draft, not in force. This text is a placeholder and does not bind anyone.",
  notFound: "This document does not exist.",
  failed: "The document could not be loaded. Try again in a moment.",
  loading: "Loading…",
  back: "All documents",
  language: "Language",
  languageNames: { en: "English", fi: "Suomi" },
  acceptance: { required: "You accept it for your Organization", notice: "Owners are notified of changes", none: "For information" },
  signup: {
    heading: "Agreements",
    accept: (title) => `I accept the ${title} for this Organization`,
    read: "(opens in a new tab)",
    failed: "Accepting the documents failed. Reload the page and try again.",
  },
  owner: {
    title: "Legal documents",
    description: "The terms and agreements your Organization has accepted. Only Owners see this and can accept a new version.",
    version: (version) => `Version ${version}`,
    accepted: (version, when, who) => `Version ${version} accepted on ${when} by ${who}`,
    formerMember: "a former member",
    notAccepted: "Not accepted yet",
    due: "A new version is waiting for your acceptance",
    accept: "Accept this version",
    accepting: "Saving…",
    open: "Read",
    failed: "The legal documents could not be saved or loaded. Try again.",
    banner: (titles) => `A new version is in force and needs an Owner's acceptance: ${titles}.`,
    bannerAction: "Review and accept",
  },
};

const fi: Copy = {
  footerLink: "Ehdot ja tietosuoja",
  indexTitle: "Ehdot, tietosuoja ja tietoturva",
  indexIntro: "Yearclock-palvelua koskevat asiakirjat.",
  indexEmpty: "Asiakirjoja ei ole vielä julkaistu.",
  version: (version, date) => `Versio ${version}, voimassa ${date} alkaen`,
  draftBanner: "Luonnos, ei voimassa. Teksti on paikkamerkki, eikä se sido ketään.",
  notFound: "Asiakirjaa ei ole olemassa.",
  failed: "Asiakirjaa ei voitu ladata. Yritä hetken kuluttua uudelleen.",
  loading: "Ladataan…",
  back: "Kaikki asiakirjat",
  language: "Kieli",
  languageNames: { en: "English", fi: "Suomi" },
  acceptance: { required: "Hyväksyt sen organisaatiollesi", notice: "Omistajille ilmoitetaan muutoksista", none: "Tiedoksi" },
  signup: {
    heading: "Sopimukset",
    accept: (title) => `Hyväksyn asiakirjan ${title} tälle organisaatiolle`,
    read: "(avautuu uuteen välilehteen)",
    failed: "Asiakirjojen hyväksyminen epäonnistui. Lataa sivu uudelleen ja yritä uudelleen.",
  },
  owner: {
    title: "Lakiasiakirjat",
    description: "Ehdot ja sopimukset, jotka organisaatiosi on hyväksynyt. Vain omistajat näkevät tämän ja voivat hyväksyä uuden version.",
    version: (version) => `Versio ${version}`,
    accepted: (version, when, who) => `Versio ${version} hyväksytty ${when}, hyväksyjä ${who}`,
    formerMember: "entinen jäsen",
    notAccepted: "Ei vielä hyväksytty",
    due: "Uusi versio odottaa hyväksyntääsi",
    accept: "Hyväksy tämä versio",
    accepting: "Tallennetaan…",
    open: "Lue",
    failed: "Lakiasiakirjoja ei voitu tallentaa tai ladata. Yritä uudelleen.",
    banner: (titles) => `Uusi versio on voimassa ja vaatii omistajan hyväksynnän: ${titles}.`,
    bannerAction: "Tarkista ja hyväksy",
  },
};

export function legalMessages(locale: Locale): Copy {
  return locale === "fi" ? fi : en;
}
