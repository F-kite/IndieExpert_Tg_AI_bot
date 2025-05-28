const dbName = process.env.MONGODB_DB_NAME;
const botName = process.env.MONGO_BOT_USERNAME;
const botPass = process.env.MONGO_BOT_PASSWORD;

db = db.getSiblingDB(dbName);
db.createUser({
  user: botName,
  pwd: botPass,
  roles: [
    {
      role: "readWrite",
      db: dbName,
    },
  ],
});
