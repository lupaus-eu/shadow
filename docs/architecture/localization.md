# Localization

## Supported locales

The first release supports:

- Finnish
- English

Each Organization has a default locale. Each User Account may override the interface language and formatting preference.

## Translation boundary

- Interface strings are translated through a frontend internationalization layer.
- UI copy is not embedded directly in React components.
- Dates and numbers use locale-aware formatting.
- User-created names, descriptions, Categories, Lanes, Events, and other content are stored and displayed exactly as entered.
- The service does not automatically translate customer content.

## Fallback

English is the source and fallback locale when a translation key is missing.
