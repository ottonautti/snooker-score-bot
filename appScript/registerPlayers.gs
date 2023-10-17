/*
Google Sheets helper scripts
*/

const playerRegistrationEventLabel = "SETUP_playerRegistration";

var results = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("_results");
const resultTableHeaders = results.getRange(1, 1, 1, results.getLastColumn()).getValues()[0];
const resultTableMap = new Map(resultTableHeaders.map((el, i) => [el, i]));
const roundsRange = SpreadsheetApp.getActiveSpreadsheet().getRangeByName("nr_rounds");
const roundsDateBounds = new Map(
    roundsRange.offset(0, 1, roundsRange.getNumRows(), 2).getValues().map((el, i) => [i + 1, el])
);

function filterRegistrationsForRound(round) {
    var filter = results.getFilter();
    if (filter) {
        filter.remove();
    }
    var criteria1 = SpreadsheetApp.newFilterCriteria().whenNumberEqualTo(round).build();
    var criteria2 = SpreadsheetApp.newFilterCriteria().whenTextEqualTo(playerRegistrationEventLabel).build();
    results.getDataRange().createFilter().setColumnFilterCriteria(resultTableMap.get("round") + 1, criteria1);
    results.getDataRange().getFilter().setColumnFilterCriteria(resultTableMap.get("source") + 1, criteria2);
}

function hideRegistrationEntries() {
    var filter = results.getFilter();
    if (filter) {
        filter.remove();
    }
    // Sets the values to hide and applies the criteria to column C.
    let criteria = SpreadsheetApp.newFilterCriteria().setHiddenValues([playerRegistrationEventLabel]).build();
    results.getDataRange().createFilter().setColumnFilterCriteria(resultTableMap.get("source") + 1, criteria);
}

// clear all registrations for a given round
function clearRegistrations(round) {
    // filter for rows where source is PLAYER REGISTRATION and round is the given round
    filterRegistrationsForRound(round);
    // delete all rows
    results.deleteRows(2, results.getLastRow() - 1);
    // remove filter
    hideRegistrationEntries();
}

function registerPlayers(round) {
    var players = SpreadsheetApp.getActiveSpreadsheet().getRangeByName("nr_currentPlayers");
    var rounds = SpreadsheetApp.getActiveSpreadsheet().getRangeByName("nr_rounds");

    // filter for empty player names
    var playerNames = players.offset(0, 0, players.getNumRows(), 1).getValues().filter(function(row) {
        return row[0] != "";
    });
    var numPlayers = playerNames.length;
    var playerGroups = players.offset(0, 1, numPlayers, 1).getValues();

    var nextAvailableRow = results.getRange(results.getLastRow() + 1, 1).getRow();

    var targetRangeSource = results.getRange(nextAvailableRow, resultTableMap.get("source") + 1, numPlayers);
    var targetRangePlayer = results.getRange(nextAvailableRow, resultTableMap.get("player 1") + 1, numPlayers);
    var targetRangeGroup = results.getRange(nextAvailableRow, resultTableMap.get("group") + 1, numPlayers);
    var targetRangeDate = results.getRange(nextAvailableRow, resultTableMap.get("date") + 1, numPlayers);

    targetRangeSource.setValues(new Array(numPlayers).fill([[playerRegistrationEventLabel]]));
    let roundsFirstDate = roundsDateBounds.get(round)[0];
    targetRangeDate.setValues(new Array(numPlayers).fill([[roundsFirstDate]]));
    targetRangePlayer.setValues(playerNames);
    targetRangeGroup.setValues(playerGroups);

    // format as plain text
    targetRangeGroup.setNumberFormat("@");

    return;
}

function buttonAddPlayers() {
    var selectedSheetName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
    var round = parseInt(selectedSheetName.match(/ROUND (\d+)/)[1]);
    clearRegistrations(round);
    registerPlayers(round);
}

function buttonResetPlayers() {
    var selectedSheetName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
    var round = parseInt(selectedSheetName.match(/ROUND (\d+)/)[1]);
    clearRegistrations(round);
}

function runme() {
    registerPlayers(2);
}
