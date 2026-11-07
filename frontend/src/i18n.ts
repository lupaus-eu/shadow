
export type Locale = "en" | "fi";

type OrganizationMessages = {
  title: string;
  description: string;
  organizationName: string;
  timeZone: string;
  locale: string;
  billingName: string;
  billingEmail: string;
  seats: string;
  price: (seats: number) => string;
  tax: string;
  submit: string;
  submitting: string;
  failed: string;
  pending: string;
  pendingDescription: string;
  expired: string;
  expiredDescription: string;
  active: (name: string) => string;
  ownerActive: string;
};

const translations = {
  en: {
    title: "Shadow",
    description:
      "Your authenticated workspace for structured planning across the year.",
    signedIn: "Signed in as",
    signOut: "Sign out",
    language: "Language",
    checkingSession: "Checking your session…",
    shell: { skip: "Skip to content", openMenu: "Open navigation", navigation: "Main navigation", organization: "Organization", switchOrganization: "Switch organization", allOrganizations: "All organizations", overview: "Overview", shadows: "Shadows", recent: "Recent", findShadow: "Find a Shadow", noShadows: "No Shadows", administration: "Administration", sections: { people: "People", activity: "Activity", support: "Support Access", agents: "Connect an agent", billing: "Billing and seats", settings: "Organization settings" }, account: "Account", accountMenu: (name = "") => `Account menu for ${name}`, notFound: "This page does not exist.", loading: "Loading…", descriptions: { people: "Invite people, change their roles, and see what each person can open.", activity: "What changed in the Organization, newest first.", support: "Decide whether platform support may see your content.", agents: "Let an AI agent you choose work with this Organization's Shadows, and switch that off when needed.", billing: "Seats and the subscription.", settings: "The Organization's details, its export, and its deletion." }, admin: { pendingInvitations: "Invitations", noInvitations: "No invitations yet.", invitationStatus: { pending: "Pending", accepted: "Accepted", revoked: "Revoked", superseded: "Replaced", expired: "Expired" }, name: "Name", email: "Email", role: "Role", actions: "Actions", when: "When", action: "Action", actor: "By", details: "Organization details", organizationName: "Name", timeZone: "Time zone", dangerZone: "Danger zone", noShadows: "No Shadows yet. Create the first one above.", seats: "Seats", export: { title: "Organization Export", description: "Download everything this Organization has stored as one JSON file, for handover or your own records. Only Owners can do this, and each download is recorded in Activity.", includes: "Included: the Organization, members (name, email, role), Groups, Labels, Categories, Shadows with their Lanes, Events, Series, and access.", excludes: "Left out: Event history, the Activity log, billing data, and email records.", action: "Download Organization Export", working: "Preparing the file…", failed: "The Organization Export could not be downloaded. Try again.", rateLimited: (minutes) => `You have downloaded the export too often. Try again in ${minutes} ${minutes === 1 ? "minute" : "minutes"}.`, saved: "Organization Export saved." } } },
    overlay: { cancel: "Cancel", close: "Close", dismiss: "Dismiss", notifications: "Notifications" },
    unavailable: "Shadow is temporarily unavailable.",
    sessionExpired: "Your session has expired.",
    signedOut: "You have signed out.",
    signInTitle: "Sign in to Shadow",
    signInDescription:
      "Continue to your private planning workspace. Every Shadow view requires an authenticated account.",
    signInAction: "Continue with Authentik",
    platformAccount: "You are signed in with a platform account, which cannot open customer Organizations.",
    openConsole: "Open the operator console",
    systemConnecting: "Connecting to PostgreSQL…",
    systemReady: (revision: string) =>
      `PostgreSQL ready · schema ${revision}`,
    systemUnavailable: "PostgreSQL status unavailable",
    organizationLoading: "Loading organizations…",
    organizationContextUnavailable:
      "Organizations are temporarily unavailable.",
    chooseOrganization: "Choose an organization",
    chooseOrganizationDescription:
      "Select the customer workspace you want to open.",
    organizationRole: {
      owner: "Organization Owner",
      admin: "Organization Admin",
      member: "Member",
    },
    organizationWorkspace: "Organization workspace",
    switchOrganization: "Switch organization",
    createAnotherOrganization: "Create another organization",
    organizationNotFound:
      "This organization is unavailable or you no longer have access.",
    enterOrganization: "Enter organization",
    lanesLabel: "Lanes",
    seatCapacity: {
      title: "Seat capacity",
      purchased: "Purchased",
      occupied: "Occupied",
      reserved: "Reserved",
      available: "Available",
      input: "Purchased seats",
      preview: "Preview increase",
      confirm: "Confirm and pay",
      schedule: "Schedule decrease",
      dueNow: (amount: string) => `${amount} due now`,
      pendingPayment: (seats: number) =>
        `Waiting for Stripe to confirm payment for ${seats} seats.`,
      scheduled: (seats: number, date: string) =>
        `Decrease to ${seats} seats is scheduled for ${date}.`,
      failed: "Seat capacity could not be updated. Reload and try again.",
    },
    organization: {
      title: "Create your organization",
      description:
        "Start with a private planning workspace and one blank Shadow.",
      organizationName: "Organization name",
      timeZone: "IANA time zone",
      locale: "Organization language",
      billingName: "Billing name",
      billingEmail: "Billing email",
      seats: "Seats",
      price: (seats: number) =>
        `${seats} × €30.00 per seat = €${(seats * 30).toFixed(2)} per month before tax, billed in advance`,
      tax: "Tax is calculated at checkout and shown separately on the invoice.",
      submit: "Continue to secure checkout",
      submitting: "Opening checkout…",
      failed:
        "Checkout could not be started. Please review the details and try again.",
      pending: "Waiting for verified payment",
      pendingDescription:
        "Your organization remains locked until Stripe confirms payment.",
      expired: "This checkout has expired",
      expiredDescription:
        "No organization access or membership was created. Start a new checkout.",
      active: (name: string) => `${name} is active`,
      ownerActive: "Owner seat: active",
    },
  },
  fi: {
    title: "Vuosikello",
    description:
      "Kirjautunut työtila vuoden tehtävien ja tapahtumien suunnitteluun.",
    signedIn: "Kirjautuneena:",
    signOut: "Kirjaudu ulos",
    language: "Kieli",
    checkingSession: "Tarkistetaan istuntoa…",
    shell: { skip: "Siirry sisältöön", openMenu: "Avaa navigaatio", navigation: "Päänavigaatio", organization: "Organisaatio", switchOrganization: "Vaihda organisaatiota", allOrganizations: "Kaikki organisaatiot", overview: "Yleiskuva", shadows: "Vuosikellot", recent: "Viimeksi avatut", findShadow: "Etsi vuosikelloa", noShadows: "Ei vuosikelloja", administration: "Hallinta", sections: { people: "Käyttäjät", activity: "Toimintaloki", support: "Tukipääsy", agents: "Yhdistä agentti", billing: "Laskutus ja käyttäjäpaikat", settings: "Organisaation asetukset" }, account: "Tili", accountMenu: (name = "") => `Tilivalikko: ${name}`, notFound: "Tätä sivua ei ole.", loading: "Ladataan…", descriptions: { people: "Kutsu käyttäjiä, muuta heidän roolejaan ja katso, mitä kukin voi avata.", activity: "Mitä organisaatiossa on muuttunut, uusin ensin.", support: "Päätä, saako palvelun tuki nähdä sisältönne.", agents: "Anna valitsemasi tekoälyagentin työskennellä organisaation vuosikellojen kanssa ja kytke se tarvittaessa pois.", billing: "Käyttäjäpaikat ja tilaus.", settings: "Organisaation tiedot, sen vienti ja sen poistaminen." }, admin: { pendingInvitations: "Kutsut", noInvitations: "Kutsuja ei vielä ole.", invitationStatus: { pending: "Odottaa", accepted: "Hyväksytty", revoked: "Peruttu", superseded: "Korvattu", expired: "Vanhentunut" }, name: "Nimi", email: "Sähköposti", role: "Rooli", actions: "Toiminnot", when: "Milloin", action: "Toimenpide", actor: "Tekijä", details: "Organisaation tiedot", organizationName: "Nimi", timeZone: "Aikavyöhyke", dangerZone: "Vaaravyöhyke", noShadows: "Vuosikelloja ei vielä ole. Luo ensimmäinen yllä.", seats: "Käyttäjäpaikat", export: { title: "Organisaation vienti", description: "Lataa kaikki, mitä organisaatiosi on tallentanut, yhtenä JSON-tiedostona luovutusta tai omia tietojasi varten. Vain omistajat voivat tehdä tämän, ja jokainen lataus kirjataan toimintalokiin.", includes: "Mukana: organisaatio, jäsenet (nimi, sähköposti, rooli), ryhmät, tunnisteet, kategoriat sekä vuosikellot kehineen, tapahtumineen, sarjoineen ja pääsyoikeuksineen.", excludes: "Pois jätetään: tapahtumien historia, toimintaloki, laskutustiedot ja sähköpostitietueet.", action: "Lataa organisaation vienti", working: "Valmistellaan tiedostoa…", failed: "Organisaation vientiä ei voitu ladata. Yritä uudelleen.", rateLimited: (minutes) => `Olet ladannut viennin liian monta kertaa. Yritä uudelleen ${minutes} minuutin kuluttua.`, saved: "Organisaation vienti tallennettu." } } },
    overlay: { cancel: "Peruuta", close: "Sulje", dismiss: "Hylkää", notifications: "Ilmoitukset" },
    unavailable: "Vuosikello ei ole tilapäisesti käytettävissä.",
    sessionExpired: "Istuntosi on vanhentunut.",
    signedOut: "Olet kirjautunut ulos.",
    signInTitle: "Kirjaudu Shadowiin",
    signInDescription:
      "Jatka yksityiseen suunnittelutyötilaasi. Kaikki Shadow-näkymät edellyttävät kirjautumista.",
    signInAction: "Jatka Authentikilla",
    platformAccount: "Olet kirjautunut ylläpitotilillä, jolla ei voi avata asiakasorganisaatioita.",
    openConsole: "Avaa ylläpitokonsoli",
    systemConnecting: "Yhdistetään PostgreSQL-tietokantaan…",
    systemReady: (revision: string) =>
      `PostgreSQL valmis · skeema ${revision}`,
    systemUnavailable: "PostgreSQL-tila ei ole saatavilla",
    organizationLoading: "Ladataan organisaatioita…",
    organizationContextUnavailable:
      "Organisaatiot eivät ole tilapäisesti saatavilla.",
    chooseOrganization: "Valitse organisaatio",
    chooseOrganizationDescription: "Valitse avattava asiakastyötila.",
    organizationRole: {
      owner: "Organisaation omistaja",
      admin: "Organisaation ylläpitäjä",
      member: "Jäsen",
    },
    organizationWorkspace: "Organisaation työtila",
    switchOrganization: "Vaihda organisaatiota",
    createAnotherOrganization: "Luo toinen organisaatio",
    organizationNotFound:
      "Organisaatio ei ole saatavilla tai käyttöoikeutesi on poistettu.",
    enterOrganization: "Avaa organisaatio",
    lanesLabel: "Kehät",
    seatCapacity: {
      title: "Käyttäjäpaikat",
      purchased: "Ostettu",
      occupied: "Käytössä",
      reserved: "Varattu",
      available: "Vapaana",
      input: "Ostettavat käyttäjäpaikat",
      preview: "Esikatsele korotus",
      confirm: "Vahvista ja maksa",
      schedule: "Ajasta vähennys",
      dueNow: (amount: string) => `${amount} maksetaan nyt`,
      pendingPayment: (seats: number) =>
        `Odotetaan Stripen maksuvahvistusta ${seats} käyttäjäpaikalle.`,
      scheduled: (seats: number, date: string) =>
        `Vähennys ${seats} käyttäjäpaikkaan on ajastettu päivälle ${date}.`,
      failed: "Käyttäjäpaikkoja ei voitu päivittää. Lataa sivu ja yritä uudelleen.",
    },
    organization: {
      title: "Luo organisaatiosi",
      description: "Aloita yksityisellä työtilalla ja tyhjällä vuosikellolla.",
      organizationName: "Organisaation nimi",
      timeZone: "IANA-aikavyöhyke",
      locale: "Organisaation kieli",
      billingName: "Laskutusnimi",
      billingEmail: "Laskutussähköposti",
      seats: "Käyttäjäpaikat",
      price: (seats: number) =>
        `${seats} × 30,00 € käyttäjäpaikalta = ${(seats * 30).toFixed(2).replace(".", ",")} € kuukaudessa ilman veroa, laskutus etukäteen`,
      tax: "Vero lasketaan kassalla ja näytetään laskulla erikseen.",
      submit: "Jatka suojattuun kassaan",
      submitting: "Avataan kassaa…",
      failed: "Kassaa ei voitu avata. Tarkista tiedot ja yritä uudelleen.",
      pending: "Odotetaan vahvistettua maksua",
      pendingDescription:
        "Organisaatio pysyy lukittuna, kunnes Stripe vahvistaa maksun.",
      expired: "Tämä kassakerta on vanhentunut",
      expiredDescription:
        "Organisaation käyttöoikeutta tai jäsenyyttä ei luotu. Aloita uusi kassa.",
      active: (name: string) => `${name} on aktiivinen`,
      ownerActive: "Omistajan käyttäjäpaikka: aktiivinen",
    },
  },
} satisfies Record<
  Locale,
  {
    title: string;
    description: string;
    signedIn: string;
    signOut: string;
    language: string;
    checkingSession: string;
    shell: { skip: string; openMenu: string; navigation: string; organization: string; switchOrganization: string; allOrganizations: string; overview: string; shadows: string; recent: string; findShadow: string; noShadows: string; administration: string; sections: Record<"people" | "activity" | "support" | "agents" | "billing" | "settings", string>; account: string; accountMenu: (name?: string) => string; notFound: string; loading: string; descriptions: Record<"people" | "activity" | "support" | "agents" | "billing" | "settings", string>; admin: { pendingInvitations: string; noInvitations: string; invitationStatus: Record<"pending" | "accepted" | "revoked" | "superseded" | "expired", string>; name: string; email: string; role: string; actions: string; when: string; action: string; actor: string; details: string; organizationName: string; timeZone: string; dangerZone: string; noShadows: string; seats: string; export: { title: string; description: string; includes: string; excludes: string; action: string; working: string; failed: string; rateLimited: (minutes: number) => string; saved: string } } };
    overlay: { cancel: string; close: string; dismiss: string; notifications: string };
    unavailable: string;
    sessionExpired: string;
    signedOut: string;
    signInTitle: string;
    signInDescription: string;
    signInAction: string;
    platformAccount: string;
    openConsole: string;
    systemConnecting: string;
    systemReady: (revision: string) => string;
    systemUnavailable: string;
    organization: OrganizationMessages;
    organizationLoading: string;
    organizationContextUnavailable: string;
    chooseOrganization: string;
    chooseOrganizationDescription: string;
    organizationRole: {
      owner: string;
      admin: string;
      member: string;
    };
    organizationWorkspace: string;
    switchOrganization: string;
    createAnotherOrganization: string;
    organizationNotFound: string;
    enterOrganization: string;
    lanesLabel: string;
    seatCapacity: {
      title: string;
      purchased: string;
      occupied: string;
      reserved: string;
      available: string;
      input: string;
      preview: string;
      confirm: string;
      schedule: string;
      dueNow: (amount: string) => string;
      pendingPayment: (seats: number) => string;
      scheduled: (seats: number, date: string) => string;
      failed: string;
    };
  }
>;

const storedLocaleKey = "shadow.locale";

export function messages(locale: Locale) {
  return translations[locale] ?? translations.en;
}

export function storedLocale(): Locale {
  const locale = localStorage.getItem(storedLocaleKey);
  return locale === "fi" || locale === "en" ? locale : "en";
}

export function rememberLocale(locale: Locale) {
  localStorage.setItem(storedLocaleKey, locale);
}


export type WorkspaceMessages = {
  languageEnglish: string;
  languageFinnish: string;
  invitationTitle: string;
  invitationDescription: string;
  email: string;
  role: string;
  organizationUser: string;
  administrator: string;
  owner: string;
  sendInvitation: string;
  invitationFailed: string;
  resend: string;
  revoke: string;
  invitationAccepted: string;
  invitationAccessGranted: string;
  organizationInvitation: string;
  invitationAcceptanceDescription: string;
  invitationAcceptanceFailed: string;
  acceptInvitation: string;
  activity: { title: string; area: string; areas: Record<string, string>; agentCalls: { outcomes: Record<"ok" | "refused" | "error", string>; kinds: Record<"read" | "write", string>; note: string }; empty: string; failed: string; system: string; viaSupport: string; more: string };
  notifications: { title: string; description: string; bell: (unread: number) => string; empty: string; failed: string; unreadOnly: string; markAllRead: string; markRead: string; more: string; unread: string; open: string; roles: Record<"owner" | "admin" | "member" | "editor" | "viewer", string>; canEdit: (name: string) => string; canView: (name: string) => string; viewOnly: (name: string) => string; lostAccess: (name: string) => string; roleChanged: (from: string, to: string) => string; invitationAccepted: (name: string, role: string) => string; ownerGained: (name: string) => string; ownerLost: (name: string) => string; supportRequested: (caseReference: string) => string; supportRevoked: (caseReference: string) => string; supportExpired: (caseReference: string) => string; billingGrace: (until: string) => string; billingCanceled: string; deletionScheduled: (until: string) => string; cancelScheduled: (until: string) => string; cancelUndone: string; resumed: string; contactChanged: (name: boolean, email: boolean) => string; legalPublished: (key: string, version: number, date: string, acceptance: string) => string; summary: { title: string; description: string; frequency: Record<"off" | "weekly" | "daily", string>; allShadows: string; chosenShadows: string }; settings: { title: string; link: string; description: string; inApp: string; email: string; save: string; saved: string; failed: string; groupEveryone: string; groupManagers: string; types: Record<"access_changed" | "access_removed" | "role_changed" | "invitation_accepted" | "ownership_changed" | "support_access" | "billing" | "deletion", { name: string; hint: string }> }; unknown: string };
  subscription: { title: string; manage: string; contact: { title: string; description: string; name: string; email: string; save: string; saved: string; failed: string; rateLimited: (hours: number) => string; invalid: string }; ended: string; resubscribe: { title: string; description: string; seats: string; minimum: (count: number) => string; action: string; working: string; failed: string; waiting: string; cancelled: string }; endedStatus: string; grace: (date: string) => string; readOnly: string; cancelScheduled: (date: string) => string; askOwner: string; failed: string; status: { active: (date: string) => string; activeNoDate: string; cancelScheduled: (date: string) => string; grace: (date: string) => string; readOnly: string }; cancel: { action: string; undo: string; title: string; description: (date: string) => string; consequence: string; seatDecrease: string; reason: string; reasons: Record<"none" | "too_expensive" | "not_needed" | "switching" | "other", string>; confirm: string; keep: string; done: (date: string) => string; undone: string; failed: string } };
  billingOverview: { nextCharge: { title: string; scheduled: (amount: string, date: string, seats: number | null) => string; cancelled: string; ended: string; unavailable: string; rules: string }; payments: { title: string; description: string; empty: string; unavailable: string; date: string; amount: string; status: string; reason: string; invoice: string; viewInvoice: (date: string) => string; states: Record<"paid" | "open" | "failed" | "void" | "uncollectible", string>; reasons: Record<"renewal" | "seat_increase" | "signup" | "other", string> } };
  membership: { title: string; owner: string; admin: string; member: string; remove: string; leave: string; finalOwner: string; failed: string; ownerConfirm: (name: string) => string; makeOwner: string; transfer: { action: string; title: string; description: string; person: string; choose: string; none: string; keep: string; keepHint: string; billing: string; confirm: string; done: (name: string) => string }; leaveDialog: { title: string; description: string; successor: string; choose: string; confirm: string; confirmPlain: string; onlyMember: string; done: string; failed: string } };
  accessOverview: { access: string; accessFor: (name: string) => string; none: string; whoHasAccess: string; hide: string; nobody: string; archived: string; confirmRemove: (name: string, lost: string[]) => string };
  bulkInvite: { title: string; role: string; addresses: string; hint: string; groups: string; preview: string; willInvite: (count: number) => string; skipped: string; reasons: Record<string, string>; seatsNeeded: (count: number) => string; send: (count: number) => string; sent: (count: number) => string; tooMany: string; failed: string };
  deletion: { title: string; description: string; confirm: (name: string) => string; request: string; failed: string; pending: (date: string) => string; restore: string; restored: string; restoreFailed: string };
  support: { title: string; description: string; organizationId: string; empty: string; requestedBy: string; case: string; scope: Record<"read" | "write", string>; status: Record<"pending" | "approved" | "rejected" | "revoked" | "expired", string>; hours: string; requestedHours: (hours: number) => string; until: (date: string) => string; approve: string; reject: string; revoke: string; failed: string };
  agents: { title: string; description: string; serverUrl: string; clientId: string; clientSecret: string; showSecret: string; hideSecret: string; secretMissing: string; copy: string; copied: string; stepsTitle: string; steps: string[]; responsibility: string; switchTitle: string; switchDescription: string; on: string; off: string; turnOn: string; turnOff: string; blocked: string; unavailable: string; failed: string };
};

const workspaceTranslations: Record<Locale, WorkspaceMessages> = {
  en: {
    languageEnglish: "English", languageFinnish: "Suomi", invitationTitle: "Invite people",
    invitationDescription: "Invitations reserve an available seat for seven days. Choose Member for normal Shadow access and grant Shadows after acceptance; only Owners can invite another Owner.",
    email: "Email", role: "Role", organizationUser: "Member", administrator: "Administrator", owner: "Owner", sendInvitation: "Send invitation", invitationFailed: "Invitation request failed.", resend: "Resend", revoke: "Revoke", invitationAccepted: "Invitation accepted", invitationAccessGranted: "You now have access to the Organization.", organizationInvitation: "Organization invitation", invitationAcceptanceDescription: "Accept this invitation with the account that owns the invited email address.", invitationAcceptanceFailed: "This invitation could not be accepted. It may be expired, revoked, or addressed to a different email.", acceptInvitation: "Accept invitation",
    activity: { title: "Activity", area: "Area", areas: { all: "All", organization: "Organization, people, and billing", shadow: "Shadows", lane: "Lanes", category: "Categories", label: "Labels", event: "Events", series: "Series", occurrence: "Occurrences", support_access: "Support Access", agent_calls: "Agent calls" }, agentCalls: { outcomes: { ok: "ok", refused: "refused", error: "failed" }, kinds: { read: "read", write: "write" }, note: "Every call an agent makes through MCP, for the person it acts for. Only the tool and the outcome are recorded, never what was read or written. Successful reads are kept for 90 days." }, empty: "No activity yet.", failed: "Activity could not be loaded.", system: "system", viaSupport: "through Support Access", more: "Load more" },
    notifications: { title: "Notifications", description: "What changed for you in this Organization. Notifications never include what is in an Event, and they are deleted after 90 days.", bell: (unread) => (unread > 0 ? `Notifications, ${unread} unread` : "Notifications"), empty: "No notifications.", failed: "Notifications could not be loaded.", unreadOnly: "Unread only", markAllRead: "Mark all as read", markRead: "Mark as read", more: "Load more", unread: "Unread", open: "Open", roles: { owner: "Owner", admin: "Administrator", member: "Member", editor: "Editor", viewer: "Viewer" }, canEdit: (name) => `You can now edit ${name}.`, canView: (name) => `You can now view ${name}.`, viewOnly: (name) => `Your access to ${name} changed to view only.`, lostAccess: (name) => `You no longer have access to ${name}.`, roleChanged: (from, to) => `Your role in the Organization changed from ${from} to ${to}.`, invitationAccepted: (name, role) => `${name} accepted your invitation as ${role}.`, ownerGained: (name) => `${name} is now an Owner.`, ownerLost: (name) => `${name} is no longer an Owner.`, supportRequested: (caseReference) => `Platform support asked for access to your Organization (case ${caseReference}).`, supportRevoked: (caseReference) => `Support Access for case ${caseReference} was ended.`, supportExpired: (caseReference) => `Support Access for case ${caseReference} has expired.`, billingGrace: (until) => `The latest payment failed. The subscription stays usable${until ? ` until ${until}` : ""}.`, billingCanceled: "The subscription was canceled, so the Organization is now read-only.", deletionScheduled: (until) => `Deletion of the Organization was requested${until ? `; it can be restored until ${until}` : ""}.`, cancelScheduled: (until) => `The subscription was set to end${until ? ` on ${until}` : " at the end of the paid period"}.`, cancelUndone: "The scheduled cancellation was undone. The subscription continues.", resumed: "The subscription was started again. The Organization is writable again.", contactChanged: (name, email) => `The billing contact was changed (${[name ? "name" : "", email ? "email" : ""].filter(Boolean).join(", ")}).`, legalPublished: (key, version, date, acceptance) => `Version ${version} of the ${({ terms: "terms of service", dpa: "data processing agreement", privacy: "privacy notice", storage: "browser storage notice", subprocessors: "list of sub-processors", switching: "switching and data return terms", security: "security measures", provider: "provider information" } as Record<string, string>)[key] ?? key} is published${date ? ` and takes effect on ${date}` : ""}.${acceptance === "required" ? " An Owner needs to accept it in Organization settings." : ""}`, summary: { title: "Summary of upcoming Events", description: "An email at about 8:00 Organization time with the Events starting soon in the Shadows you can read: the next 14 days on Mondays, or the next 7 days every day. Nothing is sent when there is nothing to list. Unlike other notifications it includes Event titles.", frequency: { off: "Off", weekly: "Weekly, on Mondays", daily: "Every day" }, allShadows: "All Shadows I can read", chosenShadows: "Only these Shadows" }, settings: { title: "Notification settings", link: "Settings", description: "Choose where you hear about each kind of change in this Organization. Email goes out right away, up to 10 notification emails a day.", inApp: "In the app", email: "By email", save: "Save settings", saved: "Settings saved.", failed: "The settings could not be saved.", groupEveryone: "Your access and role", groupManagers: "Organization notices", types: { access_changed: { name: "Access to a Shadow changed", hint: "You can view or edit a Shadow, or your access changed." }, access_removed: { name: "Access to a Shadow removed", hint: "You lose access to a Shadow." }, role_changed: { name: "Your role changed", hint: "Your role in the Organization changed." }, invitation_accepted: { name: "Invitation accepted", hint: "Someone you invited joined." }, ownership_changed: { name: "Ownership changed", hint: "Someone became or stopped being an Owner." }, support_access: { name: "Support Access", hint: "Platform support asks for access, or access ends." }, billing: { name: "Billing", hint: "A payment failed or the subscription was canceled." }, deletion: { name: "Organization deletion", hint: "Deletion of the Organization was requested." } } }, unknown: "Something changed." },
    subscription: { title: "Subscription", manage: "Manage billing", contact: { title: "Billing contact", description: "The name and email on invoices. The billing address, VAT ID, and payment method are in Manage billing. When the email changes, the old address gets a short notice and the other Owners and Administrators are told.", name: "Billing name", email: "Billing email", save: "Save billing contact", saved: "Billing contact saved.", failed: "The billing contact could not be saved. Try again.", rateLimited: (hours) => `The billing contact was changed too often. Try again in about ${hours} ${hours === 1 ? "hour" : "hours"}.`, invalid: "Enter a name and an email address." }, ended: "This Organization is read-only because its subscription has ended. Content stays available to view; an Owner can subscribe again in Billing and seats.", endedStatus: "The subscription has ended. The Organization is read-only and its content is kept.", resubscribe: { title: "Subscribe again", description: "Buy a new subscription to make the Organization writable again. Nothing is lost: all Shadows, Events, and people are still here.", seats: "Seats", minimum: (count) => `At least ${count}, the people and invitations the Organization has now.`, action: "Continue to payment", working: "Opening payment…", failed: "Payment could not be started. Try again.", waiting: "Waiting for the payment to be confirmed. This page updates by itself.", cancelled: "Payment was not completed. You can try again." }, grace: (date) => `A renewal payment failed. Everything keeps working until ${date}; an Owner must update the payment details before then.`, readOnly: "This Organization is read-only because its subscription is not paid. Content stays available to view; an Owner can restore editing by paying in the billing portal.", cancelScheduled: (date) => `The subscription is cancelled and ends on ${date}. Content stays; an Owner can undo the cancellation in Billing and seats.`, askOwner: "Ask an Organization Owner to resolve billing.", failed: "The billing portal could not be opened.", status: { active: (date) => `Active. The next payment is on ${date}.`, activeNoDate: "Active.", cancelScheduled: (date) => `Cancellation scheduled: the subscription ends on ${date}.`, grace: (date) => `A renewal payment failed. Everything keeps working until ${date}.`, readOnly: "Read-only: the subscription is not paid." }, cancel: { action: "Cancel subscription", undo: "Undo cancellation", title: "Cancel the subscription?", description: (date) => `The subscription ends at the end of the paid period${date ? `, on ${date}` : ""}. Until then everything keeps working.`, consequence: "After that the Organization is read-only: people can still view the content and an Owner can still download the Organization Export. Nothing is deleted, and an Owner can subscribe again.", seatDecrease: "A scheduled seat decrease is released because the subscription ends.", reason: "Why are you cancelling? (optional)", reasons: { none: "I would rather not say", too_expensive: "It costs too much", not_needed: "We no longer need it", switching: "We are switching to another tool", other: "Another reason" }, confirm: "Cancel subscription", keep: "Keep subscription", done: (date) => `The subscription ends on ${date}.`, undone: "The cancellation was undone. The subscription continues.", failed: "The subscription could not be changed. Try again." } },
    billingOverview: { nextCharge: { title: "Next charge", scheduled: (amount, date, seats) => `${amount} on ${date}${seats === null ? "" : `, for ${seats} ${seats === 1 ? "seat" : "seats"}`}.`, cancelled: "No further charge: the subscription ends at the end of the paid period.", ended: "No further charge: the subscription has ended.", unavailable: "The next charge could not be loaded from Stripe right now.", rules: "A seat you add is charged at once for the days left in the month. A seat you remove stays paid until the period ends. Nothing is refunded." }, payments: { title: "Payments", description: "The latest invoices, read from Stripe.", empty: "There are no invoices yet.", unavailable: "The payments could not be loaded from Stripe right now. The rest of this page works.", date: "Date", amount: "Amount", status: "Status", reason: "Reason", invoice: "Invoice", viewInvoice: (date) => `View the invoice of ${date}`, states: { paid: "Paid", open: "Open", failed: "Failed", void: "Void", uncollectible: "Uncollectible" }, reasons: { renewal: "Monthly renewal", seat_increase: "Seats added", signup: "New subscription", other: "Other" } } },
    membership: { title: "People", owner: "Owner", admin: "Administrator", member: "Member", remove: "Remove", leave: "Leave", finalOwner: "The only Owner: transfer ownership before leaving or stepping down.", failed: "People could not be updated.", ownerConfirm: (name) => `Make ${name} an Owner? Owners manage billing and the subscription, can delete the Organization, and can make or remove other Owners.`, makeOwner: "Make Owner", transfer: { action: "Transfer ownership", title: "Transfer ownership", description: "Choose who becomes an Owner. Owners manage billing and the subscription, can delete the Organization, and can make or remove other Owners.", person: "New Owner", choose: "Choose a person", none: "There is no Administrator or Member to transfer to. Invite someone first.", keep: "Keep me as an Owner", keepHint: "If you do not keep it, you become an Administrator.", billing: "The billing contact is not changed. Check it in Billing and seats.", confirm: "Transfer ownership", done: (name) => `${name} is now an Owner.` }, leaveDialog: { title: "Leave this Organization?", description: "You lose access to its Shadows and your seat is released.", successor: "You are the only Owner. Choose who becomes an Owner when you leave.", choose: "Choose a successor", confirm: "Transfer and leave", confirmPlain: "Leave", onlyMember: "You are the only person here, so you cannot leave. Invite someone first, or delete the Organization in Organization settings.", done: "You left the Organization.", failed: "You could not leave the Organization." } },
    accessOverview: { access: "Access", accessFor: (name) => `Access for ${name}`, none: "Cannot open any Shadow.", whoHasAccess: "Who has access", hide: "Hide", nobody: "Nobody but Owners and Administrators.", archived: "archived", confirmRemove: (name, lost) => (lost.length ? `Remove ${name} from the Organization? They lose access to: ${lost.join(", ")}. Their Group memberships and direct access are removed too.` : `Remove ${name} from the Organization?`) },
    bulkInvite: { title: "Invite several people", role: "Invite everyone as", addresses: "Email addresses", hint: "Paste up to 50 addresses, separated by commas, semicolons, or new lines. Everyone gets the same role and Groups.", groups: "Groups to join", preview: "Preview", willInvite: (count) => (count === 1 ? "1 person will be invited." : `${count} people will be invited.`), skipped: "Skipped:", reasons: { invalid: "not a valid address", duplicate: "listed twice", member: "already a member", invited: "already invited" }, seatsNeeded: (count) => (count === 1 ? "1 more seat is needed before these invitations can be sent. Nothing has been sent." : `${count} more seats are needed before these invitations can be sent. Nothing has been sent.`), send: (count) => (count === 1 ? "Send 1 invitation" : `Send ${count} invitations`), sent: (count) => (count === 1 ? "1 invitation sent." : `${count} invitations sent.`), tooMany: "Paste at most 50 addresses at a time.", failed: "The invitations could not be sent." },
    deletion: { title: "Delete Organization", description: "Deleting closes the Organization for everyone at once. An Owner can restore it for 30 days; after that all Shadows, Events, people, and invitations are permanently purged. Billing is separate: cancel the subscription in the billing portal if you no longer want to pay. Invoices and a minimal record of the deletion are kept as the law requires.", confirm: (name) => `I understand that “${name}” is closed now and purged after 30 days.`, request: "Delete Organization", failed: "The Organization could not be deleted.", pending: (date) => `Pending deletion — purged on ${date}`, restore: "Restore", restored: "Organization restored.", restoreFailed: "The Organization could not be restored. The recovery window may have ended." },
    support: { title: "Support Access", description: "Platform support sees your content only after an Owner or Administrator approves a request. A grant covers every Shadow, is read-only unless write access was requested, ends automatically, and can be revoked at any time. Everything support does appears in Activity.", organizationId: "Organization ID for support cases", empty: "No Support Access requests.", requestedBy: "Requested by", case: "Case", scope: { read: "read only", write: "read and edit Events" }, status: { pending: "waiting for a decision", approved: "active", rejected: "rejected", revoked: "revoked", expired: "expired" }, hours: "Approve for hours", requestedHours: (hours) => `requested for ${hours} h`, until: (date) => `until ${date}`, approve: "Approve", reject: "Reject", revoke: "Revoke now", failed: "Support Access could not be updated." },
    agents: { title: "Connect an agent", description: "Let an AI agent you choose read and change this Organization's Shadows through MCP. The agent works with the signed-in person's own rights and Shadow adds no approval step of its own, so use your agent's confirmation settings.", serverUrl: "Server address", clientId: "Client ID", clientSecret: "Client secret", showSecret: "Show the secret", hideSecret: "Hide the secret", secretMissing: "The client secret has not been set up on this server. Ask the operator.", copy: "Copy", copied: "Copied", stepsTitle: "In Claude, as an example", steps: ["Add a custom connector in Claude's connector settings.", "Paste the server address as the connector address.", "Open the advanced settings and enter the client ID and the client secret.", "Connect and sign in with your own Shadow account. You must have signed in to the Shadow web application at least once."], responsibility: "Every change an agent makes is saved at once, under the rights of the person who signed in, and is recorded in Activity and the Event history as made through MCP.", switchTitle: "Agent access for this Organization", switchDescription: "When it is off, every MCP request for this Organization is refused, whoever makes it. The web application is not affected.", on: "On", off: "Off", turnOn: "Turn on", turnOff: "Turn off", blocked: "The operator has blocked agent access to this Organization. It cannot be turned on here.", unavailable: "Agent access is not enabled on this server.", failed: "The agent settings could not be loaded or saved." },
  },
  fi: {
    languageEnglish: "English", languageFinnish: "Suomi", invitationTitle: "Kutsu ihmisiä", invitationDescription: "Kutsut varaavat vapaan käyttäjäpaikan seitsemäksi päiväksi. Valitse jäsen tavalliseen Shadow-käyttöön ja myönnä vuosikellot hyväksynnän jälkeen; vain omistaja voi kutsua toisen omistajan.", email: "Sähköposti", role: "Rooli", organizationUser: "Jäsen", administrator: "Ylläpitäjä", owner: "Omistaja", sendInvitation: "Lähetä kutsu", invitationFailed: "Kutsupyyntö epäonnistui.", resend: "Lähetä uudelleen", revoke: "Peruuta", invitationAccepted: "Kutsu hyväksytty", invitationAccessGranted: "Sinulla on nyt pääsy organisaatioon.", organizationInvitation: "Organisaatiokutsu", invitationAcceptanceDescription: "Hyväksy kutsu tilillä, jonka sähköpostiosoite vastaa kutsuttua osoitetta.", invitationAcceptanceFailed: "Kutsua ei voitu hyväksyä. Se voi olla vanhentunut, peruttu tai osoitettu toiseen sähköpostiosoitteeseen.", acceptInvitation: "Hyväksy kutsu",
    activity: { title: "Toiminta", area: "Alue", areas: { all: "Kaikki", organization: "Organisaatio, käyttäjät ja laskutus", shadow: "Vuosikellot", lane: "Kehät", category: "Kategoriat", label: "Tunnisteet", event: "Tapahtumat", series: "Sarjat", occurrence: "Esiintymät", support_access: "Tukipääsy", agent_calls: "Agenttikutsut" }, agentCalls: { outcomes: { ok: "onnistui", refused: "evätty", error: "epäonnistui" }, kinds: { read: "luku", write: "kirjoitus" }, note: "Jokainen kutsu, jonka agentti tekee MCP:n kautta sen henkilön puolesta, jonka nimissä se toimii. Kirjataan vain työkalu ja tulos, ei sitä mitä luettiin tai kirjoitettiin. Onnistuneet lukukutsut säilytetään 90 päivää." }, empty: "Ei vielä toimintaa.", failed: "Toimintaa ei voitu ladata.", system: "järjestelmä", viaSupport: "tukipääsyn kautta", more: "Lataa lisää" },
    notifications: { title: "Ilmoitukset", description: "Mitä tässä organisaatiossa on muuttunut sinun kannaltasi. Ilmoituksissa ei koskaan ole tapahtumien sisältöä, ja ne poistetaan 90 päivän kuluttua.", bell: (unread) => (unread > 0 ? `Ilmoitukset, ${unread} lukematta` : "Ilmoitukset"), empty: "Ei ilmoituksia.", failed: "Ilmoituksia ei voitu ladata.", unreadOnly: "Vain lukemattomat", markAllRead: "Merkitse kaikki luetuiksi", markRead: "Merkitse luetuksi", more: "Lataa lisää", unread: "Lukematon", open: "Avaa", roles: { owner: "Omistaja", admin: "Ylläpitäjä", member: "Jäsen", editor: "Muokkaaja", viewer: "Lukija" }, canEdit: (name) => `Voit nyt muokata vuosikelloa ${name}.`, canView: (name) => `Voit nyt katsoa vuosikelloa ${name}.`, viewOnly: (name) => `Pääsysi vuosikelloon ${name} muuttui vain katseluksi.`, lostAccess: (name) => `Sinulla ei ole enää pääsyä vuosikelloon ${name}.`, roleChanged: (from, to) => `Roolisi organisaatiossa muuttui: ${from} → ${to}.`, invitationAccepted: (name, role) => `${name} hyväksyi kutsusi roolilla ${role}.`, ownerGained: (name) => `${name} on nyt omistaja.`, ownerLost: (name) => `${name} ei ole enää omistaja.`, supportRequested: (caseReference) => `Palvelun tuki pyysi pääsyä organisaatioosi (tapaus ${caseReference}).`, supportRevoked: (caseReference) => `Tukipääsy tapaukseen ${caseReference} päätettiin.`, supportExpired: (caseReference) => `Tukipääsy tapaukseen ${caseReference} vanheni.`, billingGrace: (until) => `Viimeisin maksu epäonnistui. Tilaus pysyy käytössä${until ? ` ${until} asti` : ""}.`, billingCanceled: "Tilaus peruttiin, joten organisaatio on nyt vain luettavissa.", deletionScheduled: (until) => `Organisaation poistoa pyydettiin${until ? `; sen voi palauttaa ${until} asti` : ""}.`, cancelScheduled: (until) => `Tilaus asetettiin päättymään${until ? ` ${until}` : " maksetun jakson lopussa"}.`, cancelUndone: "Ajastettu peruutus kumottiin. Tilaus jatkuu.", resumed: "Tilaus aloitettiin uudelleen. Organisaatiota voi taas muokata.", contactChanged: (name, email) => `Laskutusyhteys muuttui (${[name ? "nimi" : "", email ? "sähköposti" : ""].filter(Boolean).join(", ")}).`, legalPublished: (key, version, date, acceptance) => `Asiakirjasta ${({ terms: "palveluehdot", dpa: "tietojenkäsittelysopimus", privacy: "tietosuojaseloste", storage: "selaintallennusseloste", subprocessors: "alikäsittelijäluettelo", switching: "palvelun vaihdon ja tietojen palautuksen ehdot", security: "tietoturvatoimet", provider: "palveluntarjoajan tiedot" } as Record<string, string>)[key] ?? key} on julkaistu versio ${version}${date ? `, joka tulee voimaan ${date}` : ""}.${acceptance === "required" ? " Omistajan on hyväksyttävä se organisaation asetuksissa." : ""}`, summary: { title: "Yhteenveto tulevista tapahtumista", description: "Sähköposti noin klo 8 organisaation aikaa, jossa on lähiaikojen tapahtumat vuosikelloista, joita voit lukea: maanantaisin seuraavat 14 päivää tai joka päivä seuraavat 7 päivää. Mitään ei lähetetä, jos listattavaa ei ole. Toisin kuin muut ilmoitukset se sisältää tapahtumien otsikot.", frequency: { off: "Pois", weekly: "Viikoittain, maanantaisin", daily: "Joka päivä" }, allShadows: "Kaikki vuosikellot, joita voin lukea", chosenShadows: "Vain nämä vuosikellot" }, settings: { title: "Ilmoitusasetukset", link: "Asetukset", description: "Valitse, missä kuulet kustakin muutoksesta tässä organisaatiossa. Sähköposti lähtee heti, enintään 10 ilmoitussähköpostia päivässä.", inApp: "Sovelluksessa", email: "Sähköpostilla", save: "Tallenna asetukset", saved: "Asetukset tallennettu.", failed: "Asetuksia ei voitu tallentaa.", groupEveryone: "Pääsysi ja roolisi", groupManagers: "Organisaation ilmoitukset", types: { access_changed: { name: "Pääsy vuosikelloon muuttui", hint: "Voit katsoa tai muokata vuosikelloa, tai pääsysi muuttui." }, access_removed: { name: "Pääsy vuosikelloon poistui", hint: "Menetät pääsyn vuosikelloon." }, role_changed: { name: "Roolisi muuttui", hint: "Roolisi organisaatiossa muuttui." }, invitation_accepted: { name: "Kutsu hyväksyttiin", hint: "Kutsumasi henkilö liittyi." }, ownership_changed: { name: "Omistajuus muuttui", hint: "Joku tuli omistajaksi tai lakkasi olemasta omistaja." }, support_access: { name: "Tukipääsy", hint: "Palvelun tuki pyytää pääsyä tai pääsy päättyy." }, billing: { name: "Laskutus", hint: "Maksu epäonnistui tai tilaus peruttiin." }, deletion: { name: "Organisaation poisto", hint: "Organisaation poistoa pyydettiin." } } }, unknown: "Jokin muuttui." },
    subscription: { title: "Tilaus", manage: "Hallitse laskutusta", contact: { title: "Laskutusyhteys", description: "Laskuilla näkyvä nimi ja sähköposti. Laskutusosoite, ALV-tunnus ja maksutapa ovat kohdassa Hallitse laskutusta. Kun sähköposti vaihtuu, vanhaan osoitteeseen lähtee lyhyt ilmoitus ja muille omistajille ja ylläpitäjille kerrotaan.", name: "Laskutusnimi", email: "Laskutussähköposti", save: "Tallenna laskutusyhteys", saved: "Laskutusyhteys tallennettu.", failed: "Laskutusyhteyttä ei voitu tallentaa. Yritä uudelleen.", rateLimited: (hours) => `Laskutusyhteyttä on muutettu liian usein. Yritä uudelleen noin ${hours} tunnin kuluttua.`, invalid: "Anna nimi ja sähköpostiosoite." }, ended: "Organisaatio on vain luku -tilassa, koska sen tilaus on päättynyt. Sisältöä voi yhä katsella; omistaja voi tilata uudelleen Laskutus ja paikat -sivulla.", endedStatus: "Tilaus on päättynyt. Organisaatio on vain luku -tilassa ja sen sisältö säilyy.", resubscribe: { title: "Tilaa uudelleen", description: "Osta uusi tilaus, niin organisaatiota voi taas muokata. Mitään ei ole menetetty: kaikki vuosikellot, tapahtumat ja ihmiset ovat tallessa.", seats: "Käyttäjäpaikat", minimum: (count) => `Vähintään ${count}, eli organisaation nykyiset ihmiset ja kutsut.`, action: "Jatka maksamaan", working: "Avataan maksua…", failed: "Maksua ei voitu aloittaa. Yritä uudelleen.", waiting: "Odotetaan maksun vahvistusta. Sivu päivittyy itsestään.", cancelled: "Maksua ei suoritettu loppuun. Voit yrittää uudelleen." }, grace: (date) => `Uusimismaksu epäonnistui. Kaikki toimii ${date} asti; omistajan on päivitettävä maksutiedot ennen sitä.`, readOnly: "Organisaatio on vain luku -tilassa, koska tilausta ei ole maksettu. Sisältöä voi yhä katsella; omistaja voi palauttaa muokkauksen maksamalla laskutusportaalissa.", cancelScheduled: (date) => `Tilaus on peruttu ja päättyy ${date}. Sisältö säilyy; omistaja voi perua peruutuksen Laskutus ja paikat -sivulla.`, askOwner: "Pyydä organisaation omistajaa hoitamaan laskutus.", failed: "Laskutusportaalia ei voitu avata.", status: { active: (date) => `Voimassa. Seuraava maksu on ${date}.`, activeNoDate: "Voimassa.", cancelScheduled: (date) => `Peruutus ajastettu: tilaus päättyy ${date}.`, grace: (date) => `Uusimismaksu epäonnistui. Kaikki toimii ${date} asti.`, readOnly: "Vain luku: tilausta ei ole maksettu." }, cancel: { action: "Peruuta tilaus", undo: "Kumoa peruutus", title: "Peruutetaanko tilaus?", description: (date) => `Tilaus päättyy maksetun jakson lopussa${date ? `, ${date}` : ""}. Siihen asti kaikki toimii.`, consequence: "Sen jälkeen organisaatio on vain luku -tilassa: ihmiset voivat yhä katsella sisältöä ja omistaja voi ladata organisaation viennin. Mitään ei poisteta, ja omistaja voi tilata uudelleen.", seatDecrease: "Ajastettu paikkojen vähennys perutaan, koska tilaus päättyy.", reason: "Miksi peruutat? (valinnainen)", reasons: { none: "En halua kertoa", too_expensive: "Se on liian kallis", not_needed: "Emme tarvitse sitä enää", switching: "Vaihdamme toiseen työkaluun", other: "Muu syy" }, confirm: "Peruuta tilaus", keep: "Pidä tilaus", done: (date) => `Tilaus päättyy ${date}.`, undone: "Peruutus kumottiin. Tilaus jatkuu.", failed: "Tilausta ei voitu muuttaa. Yritä uudelleen." } },
    billingOverview: { nextCharge: { title: "Seuraava veloitus", scheduled: (amount, date, seats) => `${date}: ${amount}${seats === null ? "" : `, ${seats} ${seats === 1 ? "käyttäjäpaikka" : "käyttäjäpaikkaa"}`}.`, cancelled: "Ei enää veloituksia: tilaus päättyy maksetun jakson lopussa.", ended: "Ei enää veloituksia: tilaus on päättynyt.", unavailable: "Seuraavaa veloitusta ei voitu ladata Stripestä juuri nyt.", rules: "Lisäämäsi paikka veloitetaan heti kuukauden jäljellä olevilta päiviltä. Poistamasi paikka pysyy maksettuna jakson loppuun. Rahaa ei palauteta." }, payments: { title: "Maksut", description: "Viimeisimmät laskut Stripestä.", empty: "Laskuja ei ole vielä.", unavailable: "Maksuja ei voitu ladata Stripestä juuri nyt. Muu sivu toimii.", date: "Päivä", amount: "Summa", status: "Tila", reason: "Syy", invoice: "Lasku", viewInvoice: (date) => `Avaa laskun ${date} sivu`, states: { paid: "Maksettu", open: "Avoin", failed: "Epäonnistunut", void: "Mitätöity", uncollectible: "Perimätön" }, reasons: { renewal: "Kuukausittainen uusiutuminen", seat_increase: "Paikkoja lisätty", signup: "Uusi tilaus", other: "Muu" } } },
    membership: { title: "Käyttäjät", owner: "Omistaja", admin: "Ylläpitäjä", member: "Jäsen", remove: "Poista", leave: "Poistu", finalOwner: "Ainoa omistaja: siirrä omistajuus ennen poistumista tai roolin laskemista.", failed: "Käyttäjiä ei voitu päivittää.", ownerConfirm: (name) => `Tehdäänkö ${name} omistajaksi? Omistajat hallitsevat laskutusta ja tilausta, voivat poistaa organisaation sekä tehdä ja poistaa muita omistajia.`, makeOwner: "Tee omistajaksi", transfer: { action: "Siirrä omistajuus", title: "Siirrä omistajuus", description: "Valitse, kuka tulee omistajaksi. Omistajat hallitsevat laskutusta ja tilausta, voivat poistaa organisaation sekä tehdä ja poistaa muita omistajia.", person: "Uusi omistaja", choose: "Valitse henkilö", none: "Ei ole ylläpitäjää tai jäsentä, jolle siirtää. Kutsu ensin joku.", keep: "Pysyn omistajana", keepHint: "Jos et pysy, sinusta tulee ylläpitäjä.", billing: "Laskutusyhteyttä ei vaihdeta. Tarkista se Laskutus ja paikat -sivulla.", confirm: "Siirrä omistajuus", done: (name) => `${name} on nyt omistaja.` }, leaveDialog: { title: "Poistutaanko organisaatiosta?", description: "Menetät pääsyn sen vuosikelloihin ja paikkasi vapautuu.", successor: "Olet ainoa omistaja. Valitse, kuka tulee omistajaksi, kun poistut.", choose: "Valitse seuraaja", confirm: "Siirrä ja poistu", confirmPlain: "Poistu", onlyMember: "Olet ainoa henkilö täällä, joten et voi poistua. Kutsu ensin joku tai poista organisaatio Organisaation asetuksissa.", done: "Poistuit organisaatiosta.", failed: "Organisaatiosta ei voitu poistua." } },
    accessOverview: { access: "Käyttöoikeudet", accessFor: (name) => `Käyttöoikeudet: ${name}`, none: "Ei voi avata yhtään vuosikelloa.", whoHasAccess: "Kenellä on pääsy", hide: "Piilota", nobody: "Vain omistajilla ja ylläpitäjillä.", archived: "arkistoitu", confirmRemove: (name, lost) => (lost.length ? `Poistetaanko ${name} organisaatiosta? Hän menettää pääsyn: ${lost.join(", ")}. Myös ryhmäjäsenyydet ja suorat oikeudet poistetaan.` : `Poistetaanko ${name} organisaatiosta?`) },
    bulkInvite: { title: "Kutsu useita henkilöitä", role: "Kutsu kaikki roolissa", addresses: "Sähköpostiosoitteet", hint: "Liitä enintään 50 osoitetta pilkuin, puolipistein tai riveittäin eroteltuina. Kaikki saavat saman roolin ja ryhmät.", groups: "Liitettävät ryhmät", preview: "Esikatsele", willInvite: (count) => (count === 1 ? "1 henkilö kutsutaan." : `${count} henkilöä kutsutaan.`), skipped: "Ohitetaan:", reasons: { invalid: "virheellinen osoite", duplicate: "listassa kahdesti", member: "jo jäsen", invited: "jo kutsuttu" }, seatsNeeded: (count) => (count === 1 ? "Kutsujen lähettämiseen tarvitaan 1 paikka lisää. Mitään ei ole lähetetty." : `Kutsujen lähettämiseen tarvitaan ${count} paikkaa lisää. Mitään ei ole lähetetty.`), send: (count) => (count === 1 ? "Lähetä 1 kutsu" : `Lähetä ${count} kutsua`), sent: (count) => (count === 1 ? "1 kutsu lähetetty." : `${count} kutsua lähetetty.`), tooMany: "Liitä kerralla enintään 50 osoitetta.", failed: "Kutsuja ei voitu lähettää." },
    deletion: { title: "Poista organisaatio", description: "Poisto sulkee organisaation heti kaikilta. Omistaja voi palauttaa sen 30 päivän ajan; sen jälkeen kaikki vuosikellot, tapahtumat, käyttäjät ja kutsut poistetaan pysyvästi. Laskutus on erillinen: peru tilaus laskutusportaalissa, jos et halua enää maksaa. Laskut ja vähimmäistieto poistosta säilytetään lain edellyttämällä tavalla.", confirm: (name) => `Ymmärrän, että ”${name}” suljetaan nyt ja poistetaan pysyvästi 30 päivän kuluttua.`, request: "Poista organisaatio", failed: "Organisaatiota ei voitu poistaa.", pending: (date) => `Odottaa poistoa — poistetaan pysyvästi ${date}`, restore: "Palauta", restored: "Organisaatio palautettu.", restoreFailed: "Organisaatiota ei voitu palauttaa. Palautusaika on voinut päättyä." },
    support: { title: "Tukipääsy", description: "Palvelun tuki näkee sisältönne vain, kun omistaja tai ylläpitäjä hyväksyy pyynnön. Pääsy koskee kaikkia vuosikelloja, on vain lukuoikeus ellei muokkausta pyydetty, päättyy automaattisesti ja sen voi perua milloin tahansa. Kaikki tuen toimet näkyvät toimintalokissa.", organizationId: "Organisaation tunnus tukipyyntöjä varten", empty: "Ei tukipääsypyyntöjä.", requestedBy: "Pyytäjä", case: "Tapaus", scope: { read: "vain luku", write: "luku ja tapahtumien muokkaus" }, status: { pending: "odottaa päätöstä", approved: "voimassa", rejected: "hylätty", revoked: "peruttu", expired: "päättynyt" }, hours: "Hyväksy tunneiksi", requestedHours: (hours) => `pyydetty ${hours} tunniksi`, until: (date) => `${date} asti`, approve: "Hyväksy", reject: "Hylkää", revoke: "Peru nyt", failed: "Tukipääsyä ei voitu päivittää." },
    agents: { title: "Yhdistä agentti", description: "Anna valitsemasi tekoälyagentin lukea ja muuttaa tämän organisaation vuosikelloja MCP:n kautta. Agentti toimii kirjautuneen henkilön omilla oikeuksilla, eikä Shadow lisää omaa hyväksyntävaihetta, joten käytä agenttisi vahvistusasetuksia.", serverUrl: "Palvelimen osoite", clientId: "Client ID", clientSecret: "Client secret", showSecret: "Näytä salaisuus", hideSecret: "Piilota salaisuus", secretMissing: "Client secretiä ei ole otettu käyttöön tällä palvelimella. Kysy operaattorilta.", copy: "Kopioi", copied: "Kopioitu", stepsTitle: "Esimerkkinä Claude", steps: ["Lisää mukautettu connector Clauden connector-asetuksissa.", "Liitä palvelimen osoite connectorin osoitteeksi.", "Avaa lisäasetukset ja syötä client ID ja client secret.", "Yhdistä ja kirjaudu omalla Shadow-tililläsi. Sinun on pitänyt kirjautua Shadowin verkkosovellukseen vähintään kerran."], responsibility: "Jokainen agentin tekemä muutos tallentuu heti kirjautuneen henkilön oikeuksilla ja kirjataan toimintalokiin ja tapahtuman historiaan MCP:n kautta tehdyksi.", switchTitle: "Agenttipääsy tälle organisaatiolle", switchDescription: "Kun se on pois päältä, jokainen tämän organisaation MCP-pyyntö hylätään tekijästä riippumatta. Verkkosovellus ei muutu.", on: "Päällä", off: "Pois", turnOn: "Kytke päälle", turnOff: "Kytke pois", blocked: "Operaattori on estänyt agenttipääsyn tähän organisaatioon. Sitä ei voi kytkeä päälle täältä.", unavailable: "Agenttipääsy ei ole käytössä tällä palvelimella.", failed: "Agenttiasetuksia ei voitu ladata tai tallentaa." },
  },
};

export function workspaceMessages(locale: Locale): WorkspaceMessages {
  return workspaceTranslations[locale] ?? workspaceTranslations.en;
}

export type PlatformMessages = {
  title: string; eyebrow: string; signInTitle: string; signInDescription: string; signIn: string; customerAccount: string; openCustomerApp: string;
  badge: string; notFound: string;
  signedIn: string; signOut: string; roles: Record<"platform_admin" | "support_agent", string>; loading: string; failed: string;
  health: string; database: string; email: string; jobs: string; webhooks: string; organizationsByStatus: string;
  queue: Record<"pending" | "processing" | "completed" | "failed", string>;
  organizations: string; name: string; status: string; subscription: string; cancelScheduled: string; seats: string; members: string; shadows: string; deletion: string; mcp: string; mcpAllowed: string; mcpOff: string; mcpBlocked: string; blockMcp: string; unblockMcp: string;
  failedJobs: string; noFailedJobs: string; type: string; attempts: string; error: string; replay: string; replayed: string;
  support: { title: string; request: string; organizationId: string; case: string; scope: string; read: string; write: string; hours: string; submit: string; requested: string; mine: string; empty: string; status: Record<"pending" | "approved" | "rejected" | "revoked" | "expired", string>; until: (date: string) => string; open: string; close: string; lanes: string; events: string; noEvents: string; audited: string };
};

const platformTranslations: Record<Locale, PlatformMessages> = {
  en: {
    badge: "Platform", notFound: "This page does not exist or your platform role cannot open it.",
    title: "Operator console", eyebrow: "shadow platform", signInTitle: "Sign in to the operator console", signInDescription: "Use your platform account. Customer accounts cannot open the console, and the console never shows customer planning content.", signIn: "Continue with Authentik", customerAccount: "You are signed in with a customer account. Sign out and use your separate platform account to open the console.", openCustomerApp: "Open the customer application",
    signedIn: "Signed in as", signOut: "Sign out", roles: { platform_admin: "Platform Admin", support_agent: "Support Agent" }, loading: "Loading…", failed: "The console could not load this information.",
    health: "Service health", database: "Database", email: "Email outbox", jobs: "Background jobs", webhooks: "Stripe webhooks", organizationsByStatus: "Organizations by status",
    queue: { pending: "pending", processing: "processing", completed: "completed", failed: "failed" },
    organizations: "Organizations", name: "Name", status: "Status", subscription: "Subscription", cancelScheduled: "cancellation scheduled", seats: "Seats", members: "Members", shadows: "Shadows", deletion: "Deletion requested", mcp: "Agent access (MCP)", mcpAllowed: "allowed", mcpOff: "off (Organization)", mcpBlocked: "blocked", blockMcp: "Block", unblockMcp: "Unblock",
    failedJobs: "Failed jobs", noFailedJobs: "No failed jobs.", type: "Type", attempts: "Attempts", error: "Last error", replay: "Replay", replayed: "Queued again.",
    support: { title: "Support Access", request: "Request access", organizationId: "Organization ID", case: "Support case reference", scope: "Scope", read: "Read only", write: "Read and edit Events", hours: "Hours (1–24)", submit: "Send request", requested: "Request sent. An Owner or Administrator of the Organization must approve it.", mine: "My requests", empty: "No requests yet.", status: { pending: "waiting for approval", approved: "active", rejected: "rejected", revoked: "revoked", expired: "expired" }, until: (date) => `until ${date}`, open: "Open content", close: "Close", lanes: "Lanes", events: "Events in the current window", noEvents: "No Events in the current window.", audited: "Every view and change is recorded in the customer's Activity." },
  },
  fi: {
    badge: "Palvelu", notFound: "Tätä sivua ei ole, tai roolisi ei voi avata sitä.",
    title: "Ylläpitokonsoli", eyebrow: "shadow-palvelu", signInTitle: "Kirjaudu ylläpitokonsoliin", signInDescription: "Käytä palvelun ylläpitotiliä. Asiakastilit eivät pääse konsoliin, eikä konsoli koskaan näytä asiakkaiden suunnittelusisältöä.", signIn: "Jatka Authentikilla", customerAccount: "Olet kirjautunut asiakastilillä. Kirjaudu ulos ja käytä erillistä ylläpitotiliäsi.", openCustomerApp: "Avaa asiakassovellus",
    signedIn: "Kirjautuneena:", signOut: "Kirjaudu ulos", roles: { platform_admin: "Palvelun ylläpitäjä", support_agent: "Tukihenkilö" }, loading: "Ladataan…", failed: "Konsoli ei voinut ladata näitä tietoja.",
    health: "Palvelun tila", database: "Tietokanta", email: "Sähköpostijono", jobs: "Taustatyöt", webhooks: "Stripe-webhookit", organizationsByStatus: "Organisaatiot tiloittain",
    queue: { pending: "odottaa", processing: "käsittelyssä", completed: "valmis", failed: "epäonnistui" },
    organizations: "Organisaatiot", name: "Nimi", status: "Tila", subscription: "Tilaus", cancelScheduled: "peruutus ajastettu", seats: "Paikat", members: "Jäsenet", shadows: "Vuosikellot", deletion: "Poistoa pyydetty", mcp: "Agenttipääsy (MCP)", mcpAllowed: "sallittu", mcpOff: "pois (organisaatio)", mcpBlocked: "estetty", blockMcp: "Estä", unblockMcp: "Salli",
    failedJobs: "Epäonnistuneet työt", noFailedJobs: "Ei epäonnistuneita töitä.", type: "Tyyppi", attempts: "Yritykset", error: "Viimeisin virhe", replay: "Aja uudelleen", replayed: "Asetettu uudelleen jonoon.",
    support: { title: "Tukipääsy", request: "Pyydä pääsyä", organizationId: "Organisaation tunnus", case: "Tukitapauksen viite", scope: "Laajuus", read: "Vain luku", write: "Luku ja tapahtumien muokkaus", hours: "Tunnit (1–24)", submit: "Lähetä pyyntö", requested: "Pyyntö lähetetty. Organisaation omistajan tai ylläpitäjän on hyväksyttävä se.", mine: "Omat pyynnöt", empty: "Ei pyyntöjä.", status: { pending: "odottaa hyväksyntää", approved: "voimassa", rejected: "hylätty", revoked: "peruttu", expired: "päättynyt" }, until: (date) => `${date} asti`, open: "Avaa sisältö", close: "Sulje", lanes: "Kehät", events: "Tapahtumat nykyisellä jaksolla", noEvents: "Nykyisellä jaksolla ei ole tapahtumia.", audited: "Jokainen katselu ja muutos kirjataan asiakkaan toimintalokiin." },
  },
};

export function platformMessages(locale: Locale): PlatformMessages {
  return platformTranslations[locale] ?? platformTranslations.en;
}
