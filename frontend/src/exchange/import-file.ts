/** The import format a file name stands for; macro workbooks and anything else are not accepted. */
export function importFormat(fileName: string): "xlsx" | "csv" | null {
  const extension = /\.([a-z0-9]+)$/i.exec(fileName.trim())?.[1]?.toLowerCase();
  if (extension === "xlsx") return "xlsx";
  return extension === "csv" || extension === "txt" ? "csv" : null;
}

/** Megabytes for a message, from the limit the server reports in bytes. */
export const megabytes = (bytes: unknown): number => Math.max(1, Math.round(Number(bytes) / (1024 * 1024)));
