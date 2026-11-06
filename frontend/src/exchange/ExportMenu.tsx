import { Download, CalendarDays, FileSpreadsheet, FileText, Image as ImageIcon, Printer, Upload } from "lucide-react";

import type { PlannerMessages } from "../i18n";
import { Button, Menu } from "../ui";

/** Print, image, and (with later tickets) file export and import for the current Yearclock. */
export function ExportMenu({ copy, importLabel, canDownloadImage, canImport, onPrint, onImage, onExport, onImport }: { copy: PlannerMessages["exchange"]; importLabel: string; canDownloadImage: boolean; canImport: boolean; onPrint: () => void; onImage: () => void; onExport: (format: "xlsx" | "csv" | "ics") => void; onImport: () => void }) {
  return (
    <Menu
      trigger={<Button size="sm" icon={<Download size={14} />}>{copy.menu}</Button>}
      items={[
        { label: copy.print, onSelect: onPrint, icon: <Printer size={14} /> },
        ...(canDownloadImage ? [{ label: copy.image, onSelect: onImage, icon: <ImageIcon size={14} /> }] : []),
        "separator" as const,
        { label: copy.exportXlsx, onSelect: () => onExport("xlsx"), icon: <FileSpreadsheet size={14} /> },
        { label: copy.exportCsv, onSelect: () => onExport("csv"), icon: <FileText size={14} /> },
        { label: copy.exportIcs, onSelect: () => onExport("ics"), icon: <CalendarDays size={14} /> },
        ...(canImport ? ["separator" as const, { label: importLabel, onSelect: onImport, icon: <Upload size={14} /> }] : []),
      ]}
    />
  );
}
