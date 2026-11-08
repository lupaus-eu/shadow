// diagram-js-minimap ships no types. `minimap.ts` is the only file that uses it, and casts what it needs.
declare module "diagram-js-minimap" {
  const module: unknown;
  export default module;
}
