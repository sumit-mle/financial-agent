# Day 2 Implementation: Database & Vector Store (Detailed)

**Date:** Day 2 of development  
**Theme:** Data persistence and vector embeddings  
**Total Commits:** 4-5 logical commits  
**Time Span:** 9 AM - 5 PM  

---

## Commit 1 (9:00 AM): PostgreSQL Setup & Connection

### What to Stage:
```
app/core/db.py                    ← Core database setup
```

### Git Commands:
```bash
git add app/core/db.py
git commit -m "Setup PostgreSQL connection pooling and health checks"
```

### File Content Highlights:
The `app/core/db.py` should contain:
- SQLAlchemy engine creation with connection pooling
- AsyncSession factory
- Database URL management from config
- Health check function for container orchestration
- Retry logic for failed connections

### What This Demonstrates:
✅ Understanding of async database patterns
✅ Production-grade connection management
✅ Docker-ready health checks

---

## Commit 2 (11:00 AM): Alembic Migrations Framework

### What to Stage:
```
alembic/                          ← Full Alembic setup
alembic/versions/001_initial.py   ← First migration
```

### Git Commands:
```bash
git add alembic/ alembic/versions/
git commit -m "Create Alembic database migration framework with initial schema"
```

### Directory Structure:
```
alembic/
├── versions/
│   └── 001_initial.py            ← Initial schema creation
├── env.py                        ← Alembic environment config
├── script.py.mako               ← Migration template
└── alembic.ini (in root)        ← Already in repo
```

### Migration Content:
The `001_initial.py` should create tables for:
- Agents (with metadata)
- Messages (conversation history)
- Experiments (A/B testing)
- Models (MLOps registry)

### What This Demonstrates:
✅ Database versioning expertise
✅ Schema design and planning
✅ Automated migration patterns

---

## Commit 3 (1:00 PM): SQLAlchemy ORM Models

### What to Stage:
```
app/models/                       ← All ORM model files
```

### Git Commands:
```bash
git add app/models/
git commit -m "Implement SQLAlchemy ORM models for agents, experiments, and data tracking"
```

### Key Files to Include:
```
app/models/
├── __init__.py
├── agent.py                     ← Agent state and metadata
├── message.py                   ← Conversation messages
├── experiment.py                ← A/B test configurations
├── model_registry.py            ← MLOps model versions
├── feedback.py                  ← User feedback data
└── analytics.py                 ← Analytics events
```

### Model Relationships:
- Agent → has many Messages
- Experiment → has many Assignments
- Model → has many Deployments
- Message → has one Feedback

### What This Demonstrates:
✅ Relational database design
✅ ORM expertise with SQLAlchemy
✅ Proper model relationships and constraints

---

## Commit 4 (3:00 PM): Qdrant Vector Store Integration

### What to Stage:
```
app/ingestion/processors/vector_store.py    ← Vector store client
```

### Git Commands:
```bash
git add app/ingestion/processors/vector_store.py
git commit -m "Implement Qdrant vector store client with collection management"
```

### Key Components:
```python
# Vector Store Client should have:
- Initialize Qdrant connection
- Create/manage collections
- Insert vectors with metadata
- Search functionality
- Delete/update operations
- Health checks
```

### Collections to Define:
1. `complaints` - Financial complaint embeddings
2. `policies` - Policy document embeddings
3. `faq` - FAQ embeddings
4. `examples` - Example responses

### What This Demonstrates:
✅ Vector database expertise
✅ Similarity search implementation
✅ Collection management patterns

---

## Commit 5 (5:00 PM): Database Utilities & Helpers

### What to Stage:
```
app/core/db.py                   ← Updated with utilities
```

### Git Commands:
```bash
git add app/core/db.py
git commit -m "Add database initialization, seeding, and health check utilities"
```

### Include:
```python
# Database utilities:
- init_db() - Create tables
- seed_db() - Load sample data
- get_db_session() - Dependency injection
- get_vector_store() - Vector store factory
- health_check() - Connection verification
```

### What This Demonstrates:
✅ Complete database lifecycle management
✅ Proper initialization patterns
✅ Testing-friendly design

---

## Full Day 2 Workflow

### Morning (9:00 - 11:00 AM)
```bash
# At 9:00 AM
git add app/core/db.py
git commit -m "Setup PostgreSQL connection pooling and health checks"

# At 10:00 AM - Write and test the database connection
# (No git action, just development)

# At 11:00 AM
git add alembic/ alembic/versions/
git commit -m "Create Alembic database migration framework with initial schema"
```

### Afternoon (1:00 - 5:00 PM)
```bash
# At 1:00 PM
git add app/models/
git commit -m "Implement SQLAlchemy ORM models for agents, experiments, and data tracking"

# At 3:00 PM
git add app/ingestion/processors/vector_store.py
git commit -m "Implement Qdrant vector store client with collection management"

# At 5:00 PM (Optional second update)
git add app/core/db.py
git commit -m "Add database initialization, seeding, and health check utilities"
```

---

## Verification Checklist

After each commit, verify:

```bash
# Check what's staged and committed
git status
git log --oneline -5

# Verify file structure
ls -la app/core/
ls -la app/models/
ls -la alembic/versions/

# Count total commits so far
git log --oneline | wc -l
```

---

## Files Modified/Created Summary

| Path | Status | Purpose |
|------|--------|---------|
| `app/core/db.py` | Modified | Database connection & health |
| `alembic/versions/001_initial.py` | Created | Schema migration |
| `app/models/agent.py` | Created | Agent ORM model |
| `app/models/message.py` | Created | Message ORM model |
| `app/models/experiment.py` | Created | Experiment ORM model |
| `app/ingestion/processors/vector_store.py` | Created | Qdrant client |

---

## Testing Between Commits

After each commit, test locally:

```bash
# After commit 1: Test DB connection
python -c "from app.core.db import get_engine; print('DB OK')"

# After commit 2: Run migrations
alembic upgrade head

# After commit 3: Verify models
python -c "from app.models import Agent; print('Models OK')"

# After commit 4: Test Qdrant
python -c "from app.ingestion.processors.vector_store import VectorStore; print('Vector store OK')"
```

---

## Common Issues & Solutions

### Issue: Alembic can't find models
**Solution:** Ensure `alembic/env.py` imports all models before `upgrade()`

### Issue: Vector store connection fails
**Solution:** Check Qdrant is running with `docker-compose ps`

### Issue: Commit message too generic
**Solution:** Use specific details (e.g., "with connection pooling" not just "setup")

---

## Moving to Day 3

When Day 2 is complete:
1. Verify 4-5 commits in git log
2. Push to remote: `git push`
3. Move to Day 3: API Foundation
4. Create fresh feature branch if needed

---

## Pro Tips for Day 2

1. **Don't rush commits** - Take time between each one
2. **Actually test** - Run the code to ensure it works
3. **Document as you go** - Add docstrings and comments
4. **Read the files** - Understand what you're committing
5. **Use meaningful names** - Help future reviewers understand

Your commit history should look like:
```
* Day2-5: Add database initialization utilities
* Day2-4: Implement Qdrant vector store
* Day2-3: Create SQLAlchemy ORM models
* Day2-2: Setup Alembic migrations
* Day2-1: Configure PostgreSQL connection
* Day1-4: (previous day's commits...)
```

This tells a clear story of database and vector store implementation! 🎉
