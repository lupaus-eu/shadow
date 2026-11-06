"""The billing contact of an Organization (Yearclock V2 P14, ADR-0032): masking and the notice to the old address."""

NOTICE = {
    "en": ("The billing email of {organization} was changed", "The billing email of {organization} on Yearclock was changed to {masked} by an Owner.\n\nIf you did not expect this, contact Yearclock support."),
    "fi": ("Organisaation {organization} laskutussähköposti vaihdettiin", "Organisaation {organization} laskutussähköposti Yearclockissa vaihdettiin osoitteeseen {masked} omistajan toimesta.\n\nJos et odottanut tätä, ota yhteyttä Yearclockin tukeen."),
}


def mask_email(address: str) -> str:
    """``billing@example.com`` becomes ``b***@e***.com``: enough to recognise, not enough to reuse."""
    local, _, domain = address.partition("@")
    host, _, suffix = domain.rpartition(".")
    if not host:
        host, suffix = domain, ""
    masked_host = f"{host[:1]}***" + (f".{suffix}" if suffix else "")
    return f"{local[:1]}***@{masked_host}"


def notice_message(locale: str, organization_name: str, new_email: str) -> tuple[str, str]:
    subject, body = NOTICE.get(locale, NOTICE["en"])
    return subject.format(organization=organization_name), body.format(organization=organization_name, masked=mask_email(new_email))
