"""The email form of a notification (Yearclock V2 P8, ADR-0031): short, no tracking, a link to the inbox and one to the settings."""
from typing import Any

ROLE_NAMES = {
    "en": {"owner": "Owner", "admin": "Administrator", "member": "Member", "editor": "Editor", "viewer": "Viewer"},
    "fi": {"owner": "Omistaja", "admin": "Ylläpitäjä", "member": "Jäsen", "editor": "Muokkaaja", "viewer": "Lukija"},
}
SENTENCES: dict[str, dict[str, Any]] = {
    "en": {
        "access_edit": "You can now edit {yearclock}.",
        "access_view": "You can now view {yearclock}.",
        "access_view_only": "Your access to {yearclock} changed to view only.",
        "access_lost": "You no longer have access to {yearclock}.",
        "role_changed": "Your role in the Organization changed from {from_role} to {to_role}.",
        "invitation_accepted": "{name} accepted your invitation as {role}.",
        "owner_gained": "{name} is now an Owner.",
        "owner_lost": "{name} is no longer an Owner.",
        "support_access_requested": "Platform support asked for access to your Organization (case {case_reference}). Approve or reject it in Support Access.",
        "support_access_revoked": "Support Access for case {case_reference} was ended.",
        "support_access_expired": "Support Access for case {case_reference} has expired.",
        "billing_grace": "The latest payment failed. Your subscription stays usable until {until}; update the payment method in Billing to keep it.",
        "billing_canceled": "The subscription was canceled, so the Organization is now read-only.",
        "deletion_scheduled": "Deletion of the Organization was requested. It can be restored until {until}.",
        "cancel_scheduled": "The subscription was set to end on {until}. Until then everything keeps working; an Owner can undo the cancellation in Billing and seats.",
        "cancel_undone": "The scheduled cancellation was undone, so the subscription continues.",
        "resumed": "The subscription was started again. The Organization is writable again with all its content.",
        "contact_changed": "The billing contact of the Organization was changed ({fields}).",
        "unknown": "Something changed.",
        "subject": "{organization}: {sentence}",
        "open": "Open your notifications:",
        "settings": "Choose which notifications you get by email:",
        "footer": "You get this email because of a change in {organization} on Yearclock.",
        "privacy": "Privacy notice:",
        "maker": "Yearclock is a service of Lupaus Palvelut Oy.",
        "legal_published": "A new version of the {document} is published and takes effect on {date}.{action}",
        "legal_action_required": " An Owner of the Organization needs to accept it in Organization settings.",
        "legal_action_notice": " This is a notice of the change.",
        "legal_notice": "You have 30 days from this message to object to the change by writing to {contact}. Read the document at {url}",
    },
    "fi": {
        "access_edit": "Voit nyt muokata vuosikelloa {yearclock}.",
        "access_view": "Voit nyt katsoa vuosikelloa {yearclock}.",
        "access_view_only": "Pääsysi vuosikelloon {yearclock} muuttui vain katseluksi.",
        "access_lost": "Sinulla ei ole enää pääsyä vuosikelloon {yearclock}.",
        "role_changed": "Roolisi organisaatiossa muuttui: {from_role} → {to_role}.",
        "invitation_accepted": "{name} hyväksyi kutsusi roolilla {role}.",
        "owner_gained": "{name} on nyt omistaja.",
        "owner_lost": "{name} ei ole enää omistaja.",
        "support_access_requested": "Palvelun tuki pyysi pääsyä organisaatioosi (tapaus {case_reference}). Hyväksy tai hylkää pyyntö Tukipääsy-sivulla.",
        "support_access_revoked": "Tukipääsy tapaukseen {case_reference} päätettiin.",
        "support_access_expired": "Tukipääsy tapaukseen {case_reference} vanheni.",
        "billing_grace": "Viimeisin maksu epäonnistui. Tilauksesi pysyy käytössä {until} asti; päivitä maksutapa Laskutus-sivulla.",
        "billing_canceled": "Tilaus peruttiin, joten organisaatio on nyt vain luettavissa.",
        "deletion_scheduled": "Organisaation poistoa pyydettiin. Sen voi palauttaa {until} asti.",
        "cancel_scheduled": "Tilaus asetettiin päättymään {until}. Siihen asti kaikki toimii; omistaja voi perua peruutuksen Laskutus ja paikat -sivulla.",
        "cancel_undone": "Ajastettu peruutus kumottiin, joten tilaus jatkuu.",
        "resumed": "Tilaus aloitettiin uudelleen. Organisaatiota voi taas muokata ja kaikki sisältö on tallessa.",
        "contact_changed": "Organisaation laskutusyhteys muuttui ({fields}).",
        "unknown": "Jokin muuttui.",
        "subject": "{organization}: {sentence}",
        "open": "Avaa ilmoituksesi:",
        "settings": "Valitse, mistä ilmoituksista saat sähköpostia:",
        "footer": "Saat tämän viestin, koska organisaatiossa {organization} tapahtui muutos Yearclockissa.",
        "privacy": "Tietosuojaseloste:",
        "maker": "Yearclock on Lupaus Palvelut Oy:n palvelu.",
        "legal_published": "Asiakirjasta {document} on julkaistu uusi versio, joka tulee voimaan {date}.{action}",
        "legal_action_required": " Organisaation omistajan on hyväksyttävä se Organisaation asetuksissa.",
        "legal_action_notice": " Tämä on ilmoitus muutoksesta.",
        "legal_notice": "Sinulla on 30 päivää tämän viestin päiväyksestä vastustaa muutosta kirjoittamalla osoitteeseen {contact}. Lue asiakirja osoitteessa {url}",
    },
}


DOCUMENT_NAMES = {
    "en": {"terms": "terms of service", "dpa": "data processing agreement", "privacy": "privacy notice", "storage": "browser storage notice", "subprocessors": "list of sub-processors", "switching": "switching and data return terms", "security": "security measures", "provider": "provider information"},
    "fi": {"terms": "palveluehdoista", "dpa": "tietojenkäsittelysopimuksesta", "privacy": "tietosuojaselosteesta", "storage": "selaintallennusselosteesta", "subprocessors": "alikäsittelijäluettelosta", "switching": "palvelun vaihdon ja tietojen palautuksen ehdoista", "security": "tietoturvatoimista", "provider": "palveluntarjoajan tiedoista"},
}


def sentence(notification_type: str, params: dict[str, Any], locale: str) -> str:
    text = SENTENCES[locale]
    role = lambda value: ROLE_NAMES[locale].get(str(value), str(value))  # noqa: E731
    name = str(params.get("yearclock_name", ""))
    if notification_type == "access_changed":
        to_role, from_role = params.get("to_role"), params.get("from_role")
        if to_role == "editor":
            return text["access_edit"].format(yearclock=name)
        if to_role == "viewer":
            return (text["access_view_only"] if from_role == "editor" else text["access_view"]).format(yearclock=name)
        return text["access_lost"].format(yearclock=name)
    if notification_type == "role_changed":
        return text["role_changed"].format(from_role=role(params.get("from_role")), to_role=role(params.get("to_role")))
    if notification_type == "invitation_accepted":
        return text["invitation_accepted"].format(name=params.get("name", ""), role=role(params.get("role")))
    if notification_type == "ownership_changed":
        return text["owner_gained" if params.get("owner") else "owner_lost"].format(name=params.get("name", ""))
    if notification_type == "support_access_requested":
        return text["support_access_requested"].format(case_reference=params.get("case_reference", ""))
    if notification_type == "support_access_ended":
        return text["support_access_expired" if params.get("how") == "expired" else "support_access_revoked"].format(case_reference=params.get("case_reference", ""))
    if notification_type == "billing_problem":
        return text["billing_canceled" if params.get("state") == "canceled" else "billing_grace"].format(until=str(params.get("grace_expires_at", ""))[:10])
    if notification_type == "subscription_cancel_scheduled":
        return text["cancel_scheduled"].format(until=str(params.get("current_period_end", ""))[:10])
    if notification_type == "billing_contact_changed":
        names = {"en": {"name": "name", "email": "email"}, "fi": {"name": "nimi", "email": "sähköposti"}}[locale]
        return text["contact_changed"].format(fields=", ".join(names.get(str(item), str(item)) for item in params.get("fields", [])))
    if notification_type == "subscription_resumed":
        return text["resumed"]
    if notification_type == "subscription_cancel_undone":
        return text["cancel_undone"]
    if notification_type == "legal_document_published":
        key = str(params.get("document_key", ""))
        action = {"required": text["legal_action_required"], "notice": text["legal_action_notice"]}.get(str(params.get("acceptance")), "")
        return text["legal_published"].format(document=DOCUMENT_NAMES[locale].get(key, key), date=str(params.get("effective_from", ""))[:10], action=action)
    if notification_type == "deletion_scheduled":
        return text["deletion_scheduled"].format(until=str(params.get("purge_after", ""))[:10])
    return text["unknown"]


def _legal_notice(notification_type: str, params: dict[str, Any], text: dict[str, Any]) -> str:
    """The 30-day objection period and the legal contact, added to the email of a legal notice."""
    if notification_type != "legal_document_published":
        return ""
    import os

    base = os.getenv("FRONTEND_URL", "http://localhost:8173").rstrip("/")
    contact = os.getenv("LEGAL_CONTACT_EMAIL", "") or "the legal contact"
    return text["legal_notice"].format(contact=contact, url=f"{base}/legal/{params.get('document_key', '')}") + "\n\n"


def render(notification_type: str, params: dict[str, Any], *, locale: str, organization_name: str, inbox_url: str, settings_url: str, privacy_url: str = "") -> tuple[str, str]:
    """Subject and plain-text body in the recipient's language."""
    locale = locale if locale in SENTENCES else "en"
    text = SENTENCES[locale]
    message = sentence(notification_type, params, locale)
    body = f"{message}\n\n{_legal_notice(notification_type, params, text)}{text['open']} {inbox_url}\n{text['settings']} {settings_url}\n\n{text['footer'].format(organization=organization_name)}\n{text['maker']}" + (f"\n{text['privacy']} {privacy_url}" if privacy_url else "")
    return text["subject"].format(organization=organization_name, sentence=message), body
