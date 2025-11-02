/**
 * Hides all sheets in the document that are prefixed with an underscore and
 * activates the last non-hidden sheet.
 */
function onOpen() {
    var sheets = SpreadsheetApp.getActiveSpreadsheet().getSheets();
    var lastSheet = sheets[0];

    sheets.forEach(function(sheet) {
        if (sheet.getName().startsWith("_")) {
            sheet.hideSheet();
        } else {
            sheet.showSheet();
            lastSheet = sheet;
        }
    });

    lastSheet.activate();
}
