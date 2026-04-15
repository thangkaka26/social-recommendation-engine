# =========================
# app.py (Flask Backend)
# =========================
import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from neo4j import GraphDatabase

app = Flask(__name__)
load_dotenv("db/.env")

# ---- CONFIG ----
URI = os.getenv("URI")
USER = os.getenv("USER")
PASSWORD = os.getenv("PASSWORD")
DATABASE = os.getenv("DATABASE")

ROOT_USER_ID = 0

# ---- DB CONNECTION ----
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# ---- HELPER ----
def run_query(query, params=None):
    with driver.session(database=DATABASE) as session:
        return list(session.run(query, params or {}))

# ---- FEED (Collaborative Filtering) ----
def get_feed():
    query = """
    MATCH (me:User {user_id:$uid})

    // ---- similar users scoring ----
    OPTIONAL MATCH (me)-[:LIKES]->(p)<-[:LIKES]-(u:User)
    WITH me, u, count(p) AS commonLikes

    OPTIONAL MATCH (me)-[:FOLLOWS]->(f)-[:FOLLOWS]->(u)
    WITH me, u, commonLikes, count(f) AS mutualFollows

    WITH me, u,
        (commonLikes * 3 + mutualFollows * 2 +
        CASE WHEN me.country = u.country THEN 2 ELSE 0 END +
        CASE WHEN me.favorite = u.favorite THEN 2 ELSE 0 END) AS simScore

    WHERE u IS NOT NULL AND u.user_id <> me.user_id

    // ---- posts from similar users ----
    MATCH (u)-[:LIKES]->(post:Post)
    MATCH (author:User)-[:CREATED]->(post)

    // keep everything before aggregation
    WITH me, post, u, simScore, author   // ADD author here

    // detect like
    OPTIONAL MATCH (me)-[l:LIKES]->(post)

    // aggregate correctly
    WITH post,
        sum(simScore) AS totalScore,
        count(DISTINCT u) AS support,
        (count(l) > 0) AS liked,
        author   // KEEP author

    // ---- FINAL RANKING ----
    WITH post,
        (totalScore + support * 2) AS finalScore,
        liked,
        author   // KEEP author

    // ---- collect all posts ----
    WITH collect({
    post: post,
    score: finalScore,
    liked: liked,
    author: author.user_name   // include author
    }) AS allPosts

    // ---- split ----
    WITH
    [x IN allPosts WHERE x.liked = false] AS normalPosts,
    [x IN allPosts WHERE x.liked = true] AS likedPosts

    // ---- shuffle liked posts (requires APOC) ----
    WITH normalPosts,
        apoc.coll.shuffle(likedPosts) AS likedPosts,
        toInteger(rand() * 4) AS k   // 0 → 3

    // ---- pick small subset ----
    WITH normalPosts,
        likedPosts[0..k] AS sampledLiked

    // ---- combine ----
    WITH normalPosts + sampledLiked AS combined

    UNWIND combined AS x

    RETURN
    x.post.post_id AS id,
    x.post.title AS title,
    x.post.content AS content,
    x.post.topic AS topic,
    x.post.created_at AS created_at,
    x.author AS author,        // ADD THIS
    x.liked AS liked,
    x.score AS score

    ORDER BY score DESC
    LIMIT 10
    """
    return run_query(query, {"uid": ROOT_USER_ID})

# ---- RECOMMENDED USERS ----
def get_users():
    query = """
CALL {

  // ---------- PART 1: CF + GRAPH ----------
  MATCH (me:User {user_id:$uid})

  OPTIONAL MATCH (me)-[:FOLLOWS]->(f:User)-[:FOLLOWS]->(u_fof:User)
  WITH me, u_fof, count(DISTINCT f) AS fofScore

  OPTIONAL MATCH (me)-[:LIKES]->(p:Post)<-[:LIKES]-(u_like:User)
  WITH me,
       u_fof,
       fofScore,
       u_like,
       count(DISTINCT p) AS likeScore

  WITH me,
       coalesce(u_fof, u_like) AS u,
       fofScore,
       likeScore

  WITH me, u,
       (fofScore * 4 +
        likeScore * 3 +
        CASE WHEN u IS NOT NULL AND u.country = me.country THEN 2 ELSE 0 END +
        CASE WHEN u IS NOT NULL AND u.favorite = me.favorite THEN 2 ELSE 0 END
       ) AS score

  WHERE u IS NOT NULL
    AND u.user_id <> me.user_id
    AND NOT (me)-[:FOLLOWS]->(u)

  RETURN
    u.user_id AS id,
    u.user_name AS name,
    u.country AS country,
    u.favorite AS favorite,
    score


  UNION


  // ---------- PART 2: FALLBACK ----------
  MATCH (me:User {user_id:$uid})
  MATCH (u:User)

  WHERE u.user_id <> me.user_id
    AND NOT (me)-[:FOLLOWS]->(u)

  RETURN
    u.user_id AS id,
    u.user_name AS name,
    u.country AS country,
    u.favorite AS favorite,
    0 AS score   // MUST MATCH PART 1
}

WITH id, name, country, favorite, max(score) AS score

RETURN id, name, country, favorite
ORDER BY score DESC, rand()
LIMIT 10
    """
    return run_query(query, {"uid": ROOT_USER_ID})

# ---- FRIEND LIST ----
def get_friends():
    query = """
    MATCH (me:User {user_id:$uid})-[:FOLLOWS]->(u)
    RETURN
    u.user_id AS id,
    u.user_name AS name,
    u.country AS country,
    u.favorite AS favorite
    """
    return run_query(query, {"uid": ROOT_USER_ID})

# ---- ACTIONS ----
@app.route("/like", methods=["POST"])
def like():
    pid = int(request.json["post_id"])
    query = """
    MATCH (me:User {user_id:$uid}), (p:Post {post_id:$pid})
    MERGE (me)-[:LIKES]->(p)
    """
    run_query(query, {"uid": ROOT_USER_ID, "pid": pid})
    return jsonify({"status":"ok"})

@app.route("/unlike", methods=["POST"])
def unlike():
    pid = int(request.json["post_id"])
    query = """
    MATCH (me:User {user_id:$uid})-[r:LIKES]->(p:Post {post_id:$pid})
    DELETE r
    """
    run_query(query, {"uid": ROOT_USER_ID, "pid": pid})
    return jsonify({"status":"ok"})

@app.route("/follow", methods=["POST"])
def follow():
    uid = int(request.json["user_id"])
    query = """
    MATCH (me:User {user_id:$uid1}), (u:User {user_id:$uid2})
    MERGE (me)-[:FOLLOWS]->(u)
    """
    run_query(query, {"uid1": ROOT_USER_ID, "uid2": uid})
    return jsonify({"status":"ok"})

@app.route("/unfollow", methods=["POST"])
def unfollow():
    uid = int(request.json["user_id"])
    query = """
    MATCH (me:User {user_id:$uid1})-[r:FOLLOWS]->(u:User {user_id:$uid2})
    DELETE r
    """
    run_query(query, {"uid1": ROOT_USER_ID, "uid2": uid})
    return jsonify({"status":"ok"})

# ---- EXPLAIN GRAPH ----
@app.route("/explain_post/<int:pid>")
def explain_post(pid):
    query = """
    MATCH (me:User {user_id:$uid})-[*1..2]-(p:Post {post_id:$pid})
    RETURN me, p
    LIMIT 20
    """
    result = run_query(query, {"uid": ROOT_USER_ID, "pid": pid})
    return jsonify([r.data() for r in result])

@app.route("/explain_user/<int:uid>")
def explain_user(uid):
    query = """
    MATCH (me:User {user_id:$uid1})-[*1..2]-(u:User {user_id:$uid2})
    RETURN me, u
    LIMIT 20
    """
    result = run_query(query, {"uid1": ROOT_USER_ID, "uid2": uid})
    return jsonify([r.data() for r in result])

@app.route("/graph/feed")
def graph_feed():
    query = """
    MATCH (me:User {user_id:0})

    OPTIONAL MATCH (me)-[:FOLLOWS]->(f:User)
    WITH me, collect(DISTINCT f) AS friends

    UNWIND friends AS f
    OPTIONAL MATCH (f)-[:CREATED]->(p:Post)

    RETURN me, f, p
    LIMIT 30
    """

    result = run_query(query)

    nodes = {}
    edges = set()

    for r in result:
        me = r.get("me")
        f = r.get("f")
        p = r.get("p")

        # --- nodes ---
        if me:
            nodes[me["user_id"]] = {
                "id": str(me["user_id"]),
                "label": me["user_name"],
                "group": "me"
            }

        if f:
            nodes[f["user_id"]] = {
                "id": str(f["user_id"]),
                "label": f["user_name"],
                "group": "user"
            }
            edges.add((
                str(me["user_id"]),
                str(f["user_id"])
            ))

        if p:
            pid = "p" + str(p["post_id"])
            nodes[pid] = {
                "id": pid,
                "label": p["title"],
                "group": "post"
            }
            edges.add((
                str(f["user_id"]),
                pid
            ))

    # ADD THIS BLOCK RIGHT BEFORE RETURN
    if len(nodes) == 0:
        nodes["0"] = {
            "id": "0",
            "label": "I Hate Neo4j",
            "group": "me"
        }

    edges = [
        {"from": f, "to": t}
        for (f, t) in edges
    ]

    return jsonify({
        "nodes": list(nodes.values()),
        "relationships": edges
    })

@app.route("/graph/users")
def graph_users():
    query = """
    MATCH (me:User {user_id:0})

    OPTIONAL MATCH (me)-[:FOLLOWS]->(f:User)
    WITH me, collect(DISTINCT f) AS friends

    UNWIND friends AS f

    OPTIONAL MATCH (f)-[:FOLLOWS]->(fof:User)

    RETURN me, f, fof
    LIMIT 30
    """

    result = run_query(query)

    nodes = {}
    edges = set()

    for r in result:
        me = r.get("me")
        f = r.get("f")
        fof = r.get("fof")

        # --- nodes ---
        if me:
            nodes[me["user_id"]] = {
                "id": str(me["user_id"]),
                "label": me["user_name"],
                "group": "me"
            }

        if f:
            nodes[f["user_id"]] = {
                "id": str(f["user_id"]),
                "label": f["user_name"],
                "group": "user"
            }

            # ALWAYS connect root → friend
            edges.add((
                str(me["user_id"]),
                str(f["user_id"])
            ))

        if fof:
            nodes[fof["user_id"]] = {
                "id": str(fof["user_id"]),
                "label": fof["user_name"],
                "group": "user"
            }

            #  friend → friend-of-friend
            edges.add((
                str(f["user_id"]),
                str(fof["user_id"])
            ))

    if len(nodes) == 0:
        nodes["0"] = {
            "id": "0",
            "label": "I Hate Neo4j",
            "group": "me"
        }

    edges = [
        {"from": f, "to": t}
        for (f, t) in edges
    ]

    return jsonify({
        "nodes": list(nodes.values()),
        "relationships": edges
    })


# ---- ROUTES ----
@app.route("/")
def home():
    return render_template(
        "home.html",
        posts=get_feed(),
        users=get_users(),
        friends=get_friends()
    )

@app.route("/friends")
def friends():
    return render_template("friends.html", friends=get_friends())

if __name__ == "__main__":
    app.run(debug=True)
