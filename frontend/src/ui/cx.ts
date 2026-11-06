import { clsx, type ClassValue } from "clsx";

/** Compose class names; later values win only by order, so keep variants explicit. */
export function cx(...values: ClassValue[]): string {
  return clsx(values);
}
