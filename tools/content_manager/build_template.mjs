import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..", "..");
const outputDir = path.join(projectRoot, "outputs", "content_template");
await fs.mkdir(outputDir, { recursive: true });

const source = JSON.parse(
  await fs.readFile(path.join(projectRoot, "resource", "content.json"), "utf8"),
);
const categories = [
  ["fortune_texts", "今日签"],
  ["colors", "幸运色"],
  ["advice_do", "宜"],
  ["advice_dont", "忌"],
];
const rows = [];
for (const [key, label] of categories) {
  for (const item of source[key]) {
    rows.push([
      label,
      item.text,
      item.min_rp ?? null,
      item.max_rp ?? null,
      "是",
      item.note ?? "",
    ]);
  }
}

const workbook = Workbook.create();
const contentSheet = workbook.worksheets.add("内容库");
const guideSheet = workbook.worksheets.add("填写说明");

contentSheet.showGridLines = false;
contentSheet.freezePanes.freezeRows(1);
contentSheet.getRange("A1:F1").values = [["类型", "内容", "RP下限", "RP上限", "启用", "备注"]];
contentSheet.getRange(`A2:F${rows.length + 1}`).values = rows;
contentSheet.getRange("A1:F1").format = {
  fill: "#315EFB",
  font: { bold: true, color: "#FFFFFF", size: 12 },
  verticalAlignment: "center",
  horizontalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: "#2448C8" },
};
contentSheet.getRange("A1:F1").format.rowHeight = 28;
contentSheet.getRange(`A2:F${rows.length + 1}`).format = {
  font: { color: "#263246", size: 11 },
  verticalAlignment: "center",
  borders: {
    insideHorizontal: { style: "thin", color: "#E6EAF0" },
    bottom: { style: "thin", color: "#D5DBE5" },
  },
};
contentSheet.getRange(`A2:A${rows.length + 1}`).format.horizontalAlignment = "center";
contentSheet.getRange(`C2:E${rows.length + 1}`).format.horizontalAlignment = "center";
contentSheet.getRange(`C2:D${rows.length + 1}`).format.numberFormat = "0";
contentSheet.getRange(`A1:A${rows.length + 1}`).format.columnWidth = 13;
contentSheet.getRange(`B1:B${rows.length + 1}`).format.columnWidth = 46;
contentSheet.getRange(`C1:D${rows.length + 1}`).format.columnWidth = 12;
contentSheet.getRange(`E1:E${rows.length + 1}`).format.columnWidth = 10;
contentSheet.getRange(`F1:F${rows.length + 1}`).format.columnWidth = 32;
contentSheet.getRange(`B2:B${rows.length + 1}`).format.wrapText = true;
contentSheet.getRange(`F2:F${rows.length + 1}`).format.wrapText = true;
contentSheet.getRange(`A2:A250`).dataValidation = {
  rule: { type: "list", values: ["今日签", "幸运色", "宜", "忌"] },
};
contentSheet.getRange(`E2:E250`).dataValidation = {
  rule: { type: "list", values: ["是", "否"] },
};
contentSheet.getRange(`C2:D250`).dataValidation = {
  rule: { type: "whole", operator: "between", formula1: 0, formula2: 100 },
};
const table = contentSheet.tables.add(`A1:F${rows.length + 1}`, true, "ContentLibraryTable");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

guideSheet.showGridLines = false;
guideSheet.getRange("A1:F1").merge();
guideSheet.getRange("A1:F1").values = [["taiko_rp 内容库填写说明"]];
guideSheet.getRange("A1:F1").format = {
  fill: "#182A54",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  horizontalAlignment: "left",
  verticalAlignment: "center",
};
guideSheet.getRange("A1:F1").format.rowHeight = 38;
guideSheet.getRange("A3:B9").values = [
  ["字段", "填写规则"],
  ["类型", "只能填写：今日签、幸运色、宜、忌"],
  ["内容", "必填；实际随机展示的文本"],
  ["RP下限", "0–100 整数；留空表示不限制最低 RP"],
  ["RP上限", "0–100 整数；留空表示不限制最高 RP"],
  ["启用", "留空或“是”表示启用；“否”表示导入时忽略"],
  ["备注", "可选，仅用于维护说明"],
];
guideSheet.getRange("A3:B3").format = {
  fill: "#E8EEFF",
  font: { bold: true, color: "#2448C8" },
};
guideSheet.getRange("A3:B9").format.borders = {
  insideHorizontal: { style: "thin", color: "#D9DFEA" },
  outside: { style: "thin", color: "#C7CFDC" },
};
guideSheet.getRange("A11:F11").merge();
guideSheet.getRange("A11:F11").values = [["示例：空白范围=任意 RP；只填下限=该值及以上；只填上限=该值及以下。导入器要求每个类型最终覆盖 RP 0–100。"]];
guideSheet.getRange("A11:F11").format = {
  fill: "#FFF5D6",
  font: { color: "#7A5610" },
  wrapText: true,
  verticalAlignment: "center",
};
guideSheet.getRange("A11:F11").format.rowHeight = 42;
guideSheet.getRange("A13:F17").values = [
  ["类型", "内容", "RP下限", "RP上限", "启用", "备注"],
  ["今日签", "大吉", 80, 100, "是", "只在高 RP 出现"],
  ["幸运色", "彩虹色", 100, 100, "是", "只在 RP=100 出现"],
  ["宜", "练习高难度谱面", 70, null, "是", "RP 70 及以上"],
  ["忌", "冲动消费", null, null, "是", "任意 RP"],
];
guideSheet.getRange("A13:F13").format = {
  fill: "#315EFB",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};
guideSheet.getRange("A14:F17").format.borders = {
  insideHorizontal: { style: "thin", color: "#E1E6EF" },
  bottom: { style: "thin", color: "#D1D8E5" },
};
guideSheet.getRange("A1:A17").format.columnWidth = 16;
guideSheet.getRange("B1:B17").format.columnWidth = 46;
guideSheet.getRange("C1:E17").format.columnWidth = 13;
guideSheet.getRange("F1:F17").format.columnWidth = 32;
guideSheet.getRange("B3:B17").format.wrapText = true;
guideSheet.getRange("F13:F17").format.wrapText = true;
guideSheet.freezePanes.freezeRows(1);

const keyRange = await workbook.inspect({
  kind: "table",
  range: `内容库!A1:F${Math.min(rows.length + 1, 14)}`,
  include: "values,formulas",
  tableMaxRows: 14,
  tableMaxCols: 6,
});
console.log(keyRange.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const sheetName of ["内容库", "填写说明"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1.25, format: "png" });
  await fs.writeFile(
    path.join(outputDir, `preview_${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "content_template.xlsx"));
console.log(path.join(outputDir, "content_template.xlsx"));
