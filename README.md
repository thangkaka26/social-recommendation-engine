# Social Recommendation Engine
A simple social networking app is powered by Python and Neo4j, with HTML UI.

## Repository layout
```
src/
├── db/
│   ├── .env
│   └── neo4j_saved_cypher_queries.csv
├── templates/
│   ├── friends.html
│   └── home.html
└── app.py
└── requirements.txt
```

## Requirements  
### Python 3:
- Flask.
- neo4j.
- dotnev.
### Neo4j 4.x:
- APOC plugin.

# SET UP TUTORIAL:
## 1) Database  
- Create and connect to an instance.
- Download APOC plugin.
- Choose your database and user.
- Import the saved cypher queries (db/neo4j_saved_cypher_queries.csv).
- Run each query from the top to bottom.
- Final check if the data is generated.

## 2) Environment variables
- Get information from your current instance in Neo4j (must be active).
- Edit connection variables in db/.env file.
- Make sure variables in .env match your current instance.

## 3) Open the app
- Make sure the directory is in correct structure as the repository and a browser window is active.
- Run app.py file.
- In the output terminal, there is a link (e.g `http://127.0.0.1:5000`).
- Open that link in your active browser.
- Once you enter, everything is done !
