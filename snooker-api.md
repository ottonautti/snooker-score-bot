# Snooker scores API

## GET /api/v1/fixtures

### Headers:
  * `Authorization: <salaisuus>`

### Responses:
* HTTP 200 OK
* HTTP 401 Unauthorized (if authorization header is missing or invalid)

### Response body schema:
```jsonc
  {
    "round": "int",  // current period number
    "matches": [
      {
        "id": "string",  // unique identifier for the fixture/match
        "format": {
          "reds": "int",   // number of red balls on the table
          "bestOf": "int", // number of frames to be played at most
        },
        "group": "string",   // group identifier
        "player1": "string", // player1 name "Lastname Firstname"
        "player2": "string", // player2 name "Lastname Firstname"
        "state": "string" // "unplayed" or "complete"
      }
    ]
  }
```

### Response body example:
```jsonc
  {
      "round": 2,
      "matches": [
        {
          "id": "y98ad",
          "format": {
            "bestOf": 3,
            "reds": "15"
          },
          "group": "L1",
          "player1": "Nikula Jani",
          "player2": "Ahonen Otto",
          "state": "unplayed"
        },
        {
          "id": "kdxcc",
          "format": {
            "bestOf": 3,
            "reds": "15"
          },
          "group": "L1",
          "player1": "Korhonen Jukka",
          "player2": "Mäkinen Jussi",
          "state": "unplayed"
        },
        {
          "id": "ef5zb",
          "format": {
            "bestOf": 3,
            "reds": "15"
          },
          "group": "L1",
          "player1": "Nikula Jani",
          "player2": "Mäkinen Jussi",
          "state": "unplayed"
        },
        {
          "id": "k44cj",
          "format": {
            "bestOf": 3,
            "reds": "15"
          },
          "group": "L1",
          "player1": "Ahonen Otto",
          "player2": "Korhonen Jukka",
          "state": "unplayed"
        },
        // ...
      ]
    }
```

## POST /api/v1/scores

### Headers:
  * `Authorization: <salaisuus>`

### Request:
```jsonc
{
  "id": "string",
  "breaks": [
    {
      "player": "string", // literal 'player1' or 'player2',
      "points": "int"
    },
    // ...
  ],
  "player1_score": "int",
  "player2_score": "int",
}
```

### Request body example:
```jsonc
  // e.g.
  {
    "id": "y98ad",
    "breaks": [
      {
        "player": "player1",
        "points": 50
      },
      {
        "player": "player2",
        "points": 30
      }
    ],
    "player1_score": 2,
    "player2_score": 1
  }
```

### Responses:
* HTTP 201 Created
* HTTP 400 Bad Request (if request is invalid)
* HTTP 401 Unauthorized (if authorization header is missing or invalid)
* HTTP 404 Not Found (if fixture not found)