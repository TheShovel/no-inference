#!/usr/bin/env python3
"""Round 10b: new-territory tasks (data, web, ops, security, leetcode, tools).

Run repair_escapes.py afterwards — patterns are raw strings here and the
JSON round-trip normalizes them.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'data' / 'knowledge' / 'code_tasks'


def load(name):
    with open(BASE / name, encoding='utf-8') as fh:
        return json.load(fh)


def _dedupe(items):
    """Keep the LAST occurrence of each task id (round-10 versions supersede)."""
    last = {}
    for i, t in enumerate(items):
        last[t['task']] = i
    return [t for i, t in enumerate(items) if last[t['task']] == i]


def save(name, data):
    if isinstance(data, dict) and 'tasks' in data:
        data['tasks'] = _dedupe(data['tasks'])
    elif isinstance(data, list):
        data = _dedupe(data)
    with open(BASE / name, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def task(data, tid):
    items = data.get('tasks', []) if isinstance(data, dict) else data
    for t in items:
        if t['task'] == tid:
            return t
    raise KeyError(tid)


def new_task(tid, patterns, intro, notes, languages, default_lang=None):
    t = {
        'task': tid,
        'patterns': patterns,
        'intro': intro,
        'notes': notes,
        'languages': languages,
    }
    if default_lang:
        t['default_lang'] = default_lang
    return t


# ── 10_sql.json: hijack guards ─────────────────────────────────────────────
d10 = load('10_sql.json')
sd = task(d10, 'sql_duplicates')
sd['patterns'] = [
    r'\bduplicate\s+rows\b',
    r'\bduplicates?\s+in\s+(?:a\s+)?table\b',
    r'^(?!.*\b(?:list|array|elements?|lines?|items?|values?)\b).*\bfind\s+duplicates?\b',
]
sg = task(d10, 'sql_group_by')
sg['patterns'] = [
    r'^(?!.*\b(?:pandas|numpy|dataframe|df)\b).*\bgroup\s+by\b',
    r'\bgrouped\s+by\b',
    r'\b(?:sum|average|count)\s+.*\bper\b',
    r'\bcount\s+rows\b',
    r'\bcount\s+records\b',
    r'\bgroup\s+(?:rows|records)\b.*\bcount\b',
    r'\bcount\s+(?:them|rows?|records?)\s+per\s+(?:group|category)\b',
]
su = task(d10, 'sql_update')
su['patterns'] = [p for p in su['patterns'] if 'join' not in p.lower()] + [
    r'^(?!.*\bjoin\b).*\bupdate\b',
]
sd_ = task(d10, 'sql_delete')
sd_['patterns'] = [p for p in sd_['patterns'] if 'join' not in p.lower()] + [
    r'^(?!.*\bjoin\b).*\bdelete\b',
]
save('10_sql.json', d10)

# ── 11_git_bash.json: commit hijack guard ──────────────────────────────────
d11 = load('11_git_bash.json')
gc = task(d11, 'git_commit')
gc['patterns'] = [p for p in gc['patterns'] if 'amend' not in p.lower()] + [
    r'^(?!.*\bamend\b).*\bcommit\b',
]
save('11_git_bash.json', d11)

# ── 17_sql_adv.json: new sql tasks ─────────────────────────────────────────
d17 = load('17_sql_adv.json')
d17.append(new_task(
    'sql_create_view',
    [r'\bcreate\s+(?:a\s+)?view\b'],
    "Here's how to create a SQL view.",
    "A view is a saved query you can SELECT from like a table. It stays in sync automatically and can hide columns or joins. Materialized views (PostgreSQL) cache the result for speed.",
    {
        'sql': "-- Create a view:\n"
               "CREATE VIEW active_customers AS\n"
               "SELECT id, name, email\n"
               "FROM customers\n"
               "WHERE active = 1;\n"
               "\n"
               "-- Use it like a table:\n"
               "SELECT * FROM active_customers;\n"
               "\n"
               "-- View over a join:\n"
               "CREATE VIEW order_totals AS\n"
               "SELECT c.name, SUM(o.total) AS total_spent\n"
               "FROM orders o\n"
               "JOIN customers c ON o.customer_id = c.id\n"
               "GROUP BY c.name;\n"
               "\n"
               "-- Replace or drop:\n"
               "CREATE OR REPLACE VIEW active_customers AS ...\n"
               "DROP VIEW IF EXISTS active_customers;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_update_join',
    [r'\bupdate\b.*\bjoin\b',
     r'\bupdate\b.*\b(?:using|with)\s+(?:a\s+)?join\b'],
    "Here's how to UPDATE rows using a JOIN in SQL.",
    "UPDATE ... FROM (PostgreSQL/SQLite) or UPDATE ... JOIN (MySQL) lets you set values from another table. SQL Server uses UPDATE ... FROM with an inner join in the same statement.",
    {
        'sql': "-- PostgreSQL / SQLite:\n"
               "UPDATE orders o\n"
               "SET o.status = 'shipped'\n"
               "FROM shipments s\n"
               "WHERE o.id = s.order_id\n"
               "  AND s.tracked_at IS NOT NULL;\n"
               "\n"
               "-- MySQL:\n"
               "UPDATE orders o\n"
               "JOIN shipments s ON o.id = s.order_id\n"
               "SET o.status = 'shipped'\n"
               "WHERE s.tracked_at IS NOT NULL;\n"
               "\n"
               "-- SQL Server:\n"
               "UPDATE o\n"
               "SET o.status = 'shipped'\n"
               "FROM orders o\n"
               "INNER JOIN shipments s ON o.id = s.order_id\n"
               "WHERE s.tracked_at IS NOT NULL;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_delete_join',
    [r'\bdelete\b.*\bjoin\b',
     r'\bdelete\b.*\b(?:using|with)\s+(?:a\s+)?join\b'],
    "Here's how to DELETE rows using a JOIN in SQL.",
    "MySQL has DELETE ... JOIN; PostgreSQL/SQLite use DELETE ... USING; SQL Server deletes via a FROM with an inner join. Always SELECT first to verify which rows match.",
    {
        'sql': "-- MySQL:\n"
               "DELETE o\n"
               "FROM orders o\n"
               "JOIN customers c ON o.customer_id = c.id\n"
               "WHERE c.active = 0;\n"
               "\n"
               "-- PostgreSQL / SQLite:\n"
               "DELETE FROM orders o\n"
               "USING customers c\n"
               "WHERE o.customer_id = c.id\n"
               "  AND c.active = 0;\n"
               "\n"
               "-- SQL Server:\n"
               "DELETE o\n"
               "FROM orders o\n"
               "INNER JOIN customers c ON o.customer_id = c.id\n"
               "WHERE c.active = 0;\n"
               "\n"
               "-- Verify first:\n"
               "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id\n"
               "WHERE c.active = 0;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_lag_lead',
    [r'\blag\s+or\s+lead\b',
     r'\b(?:lag|lead)\b.*\b(?:over|window|previous|next|row)\b'],
    "Here's how to use LAG and LEAD window functions in SQL.",
    "LAG(x) reads a value from the previous row in the window; LEAD(x) from the next row. Perfect for deltas, running comparisons, and 'previous period' calculations.",
    {
        'sql': "-- LAG: previous row's value\n"
               "SELECT\n"
               "    date,\n"
               "    revenue,\n"
               "    LAG(revenue) OVER (ORDER BY date) AS prev_revenue,\n"
               "    revenue - LAG(revenue) OVER (ORDER BY date) AS daily_delta\n"
               "FROM daily_sales;\n"
               "\n"
               "-- LEAD: next row's value\n"
               "SELECT\n"
               "    date,\n"
               "    revenue,\n"
               "    LEAD(revenue) OVER (ORDER BY date) AS next_revenue\n"
               "FROM daily_sales;\n"
               "\n"
               "-- Partitioned: per-customer deltas\n"
               "SELECT\n"
               "    customer_id,\n"
               "    order_date,\n"
               "    amount,\n"
               "    amount - LAG(amount) OVER (\n"
               "        PARTITION BY customer_id ORDER BY order_date\n"
               "    ) AS vs_previous_order\n"
               "FROM orders;\n"
               "\n"
               "-- Default when there is no previous row:\n"
               "LAG(revenue, 1, 0) OVER (ORDER BY date)  -- 0 instead of NULL"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_foreign_key',
    [r'\bforeign\s+key\b'],
    "Here's how to add a foreign key constraint in SQL.",
    "A foreign key links a column to another table's primary key and enforces referential integrity. ON DELETE CASCADE removes child rows when the parent goes; RESTRICT/SET NULL are the alternatives.",
    {
        'sql': "-- At table creation:\n"
               "CREATE TABLE orders (\n"
               "    id INTEGER PRIMARY KEY,\n"
               "    customer_id INTEGER NOT NULL,\n"
               "    total NUMERIC(10,2),\n"
               "    FOREIGN KEY (customer_id) REFERENCES customers(id)\n"
               "        ON DELETE CASCADE\n"
               ");\n"
               "\n"
               "-- Add to an existing table:\n"
               "ALTER TABLE orders\n"
               "    ADD CONSTRAINT fk_orders_customer\n"
               "    FOREIGN KEY (customer_id) REFERENCES customers(id);\n"
               "\n"
               "-- Allowed actions on delete:\n"
               "FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE   -- delete orders too\n"
               "FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL  -- set customer_id NULL\n"
               "FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT  -- block the delete\n"
               "\n"
               "-- Remove a constraint:\n"
               "ALTER TABLE orders DROP CONSTRAINT fk_orders_customer;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_top_n_per_group',
    [r'\btop\s+\d+\s+(?:salaries?|rows?|records?|employees?)\s+per\b',
     r'\btop\s+\d+\s+.*\bper\s+(?:department|group|category)\b'],
    "Here's how to get the top N rows per group in SQL.",
    "Rank rows inside each partition with ROW_NUMBER or DENSE_RANK, then filter on the rank. ROW_NUMBER gives exactly N; DENSE_RANK keeps ties.",
    {
        'sql': "-- Top 3 salaries per department (no ties):\n"
               "SELECT name, department, salary\n"
               "FROM (\n"
               "    SELECT\n"
               "        name,\n"
               "        department,\n"
               "        salary,\n"
               "        ROW_NUMBER() OVER (\n"
               "            PARTITION BY department ORDER BY salary DESC\n"
               "        ) AS rn\n"
               "    FROM employees\n"
               ") ranked\n"
               "WHERE rn <= 3;\n"
               "\n"
               "-- With ties (two employees with the same 3rd salary both show):\n"
               "SELECT name, department, salary\n"
               "FROM (\n"
               "    SELECT\n"
               "        name,\n"
               "        department,\n"
               "        salary,\n"
               "        DENSE_RANK() OVER (\n"
               "            PARTITION BY department ORDER BY salary DESC\n"
               "        ) AS dr\n"
               "    FROM employees\n"
               ") ranked\n"
               "WHERE dr <= 3;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_date_diff',
    [r'\b(?:difference|diff)\s+between\b.*\bdates?\b',
     r'\bdatediff\b',
     r'\b(?:how\s+many|number\s+of)\s+days\s+between\b'],
    "Here's how to compute the difference between two dates in SQL.",
    "DATEDIFF (MySQL/SQL Server), date subtraction (PostgreSQL), and julianday (SQLite) all give day differences. INTERVAL arithmetic handles months and years.",
    {
        'sql': "-- MySQL / SQL Server:\n"
               "SELECT DATEDIFF('2026-04-03', '2026-01-01') AS days;   -- 92\n"
               "\n"
               "-- PostgreSQL (date subtraction returns days):\n"
               "SELECT '2026-04-03'::date - '2026-01-01'::date AS days;   -- 92\n"
               "\n"
               "-- SQLite:\n"
               "SELECT julianday('2026-04-03') - julianday('2026-01-01');\n"
               "\n"
               "-- Months between (PostgreSQL):\n"
               "SELECT age('2026-04-03'::date, '2026-01-01'::date);   -- 3 mons 2 days\n"
               "\n"
               "-- Compare against today:\n"
               "SELECT * FROM orders\n"
               "WHERE order_date >= CURRENT_DATE - INTERVAL '30 days';   -- PG\n"
               "WHERE order_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY);  -- MySQL\n"
               "\n"
               "-- Age in years (PostgreSQL):\n"
               "SELECT EXTRACT(YEAR FROM age(birth_date)) AS age_years FROM people;"
    },
    default_lang='sql',
))
d17.append(new_task(
    'sql_top_n',
    [r'\btop\s+(?:\d+|n)\b.*\b(?:rows?|records?|salaries?)\b(?!.*\bper\b)',
     r'\b(?:first|top)\s+\d+\s+records?\b'],
    "Here's how to get the top N rows in SQL.",
    "LIMIT n (SQLite/PostgreSQL/MySQL) truncates the result; FETCH FIRST n ROWS ONLY is the standard SQL way. Always pair with ORDER BY or the 'top N' is arbitrary.",
    {
        'sql': "-- Top 10 by salary (SQLite / PostgreSQL / MySQL):\n"
               "SELECT *\n"
               "FROM employees\n"
               "ORDER BY salary DESC\n"
               "LIMIT 10;\n"
               "\n"
               "-- Standard SQL:\n"
               "SELECT *\n"
               "FROM employees\n"
               "ORDER BY salary DESC\n"
               "FETCH FIRST 10 ROWS ONLY;\n"
               "\n"
               "-- With ties (keeps rows equal to the 10th value):\n"
               "SELECT *\n"
               "FROM employees\n"
               "ORDER BY salary DESC\n"
               "FETCH FIRST 10 ROWS WITH TIES;\n"
               "\n"
               "-- Top N per group (window function):\n"
               "SELECT * FROM (\n"
               "    SELECT *,\n"
               "           ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rn\n"
               "    FROM employees\n"
               ") t\n"
               "WHERE rn <= 3;"
    },
    default_lang='sql',
))
save('17_sql_adv.json', d17)

# ── 13_python_utils.json: new python tasks ─────────────────────────────────
d13 = load('13_python_utils.json')
new13 = [
    new_task(
        'pandas_groupby',
        [r'\b(?:pandas|dataframe|df)\b.*\bgroup\s+by\b',
         r'\bgroup\s+by\b.*\b(?:pandas|dataframe|column)\b.*\b(?:mean|aggregate|sum)\b'],
        "Here's how to group by a column and aggregate with pandas.",
        "groupby splits the frame, applies the aggregation per group, and combines. Pass as_index=False to keep the group column, or use .agg() for several functions at once.",
        {
            'python': "import pandas as pd\n"
                      "\n"
                      "df = pd.read_csv('sales.csv')\n"
                      "\n"
                      "# Mean per group:\n"
                      "result = df.groupby('region')['revenue'].mean()\n"
                      "print(result)\n"
                      "\n"
                      "# Keep the group column (as_index=False):\n"
                      "result = df.groupby('region', as_index=False)['revenue'].mean()\n"
                      "\n"
                      "# Several aggregations:\n"
                      "result = df.groupby('region')['revenue'].agg(['mean', 'sum', 'count'])\n"
                      "\n"
                      "# Aggregate multiple columns differently:\n"
                      "result = df.groupby('region').agg(\n"
                      "    total_revenue=('revenue', 'sum'),\n"
                      "    avg_orders=('orders', 'mean'),\n"
                      ")\n"
                      "\n"
                      "# Group by multiple keys:\n"
                      "df.groupby(['region', 'year'])['revenue'].sum()"
        },
    ),
    new_task(
        'numpy_basics',
        [r'\bnumpy\b',
         r'\bnp\.array\b',
         r'\bndarray\b'],
        "Here's how to create and use NumPy arrays.",
        "np.array builds an array; np.arange/np.zeros/np.linspace create them directly. Vectorized operations run at C speed — avoid Python loops over arrays.",
        {
            'python': "import numpy as np\n"
                      "\n"
                      "# Create arrays:\n"
                      "a = np.array([1, 2, 3, 4])\n"
                      "zeros = np.zeros(5)\n"
                      "ones = np.ones((2, 3))\n"
                      "seq = np.arange(0, 10, 2)        # [0 2 4 6 8]\n"
                      "lin = np.linspace(0, 1, 5)       # 5 points 0..1\n"
                      "\n"
                      "# Vectorized math (no loops!):\n"
                      "print(a * 2)          # [2 4 6 8]\n"
                      "print(a + a)          # [2 4 6 8]\n"
                      "print(a.mean())       # 2.5\n"
                      "print(a.sum(), a.max(), a.min())\n"
                      "\n"
                      "# 2D arrays:\n"
                      "m = np.array([[1, 2], [3, 4]])\n"
                      "print(m.T)            # transpose\n"
                      "print(m @ m)          # matrix multiply\n"
                      "\n"
                      "# Boolean masks:\n"
                      "print(a[a > 2])       # [3 4]\n"
                      "\n"
                      "# Random:\n"
                      "rng = np.random.default_rng(42)\n"
                      "print(rng.normal(size=5))"
        },
    ),
    new_task(
        'matplotlib_plot',
        [r'\bmatplotlib\b',
         r'\bplot\b.*\b(?:chart|graph|line\s+chart)\b',
         r'\b(?:line\s+chart|plot)\b.*\bmatplotlib\b'],
        "Here's how to plot a line chart with Matplotlib.",
        "plt.plot + plt.show is the minimal workflow. Use fig, ax = plt.subplots() and ax.plot for full control, and savefig to export.",
        {
            'python': "import matplotlib.pyplot as plt\n"
                      "\n"
                      "x = [1, 2, 3, 4, 5]\n"
                      "y = [2, 4, 1, 8, 6]\n"
                      "\n"
                      "# Minimal line chart:\n"
                      "plt.plot(x, y)\n"
                      "plt.xlabel('Time')\n"
                      "plt.ylabel('Value')\n"
                      "plt.title('My chart')\n"
                      "plt.show()\n"
                      "\n"
                      "# With an explicit figure/axes (recommended):\n"
                      "fig, ax = plt.subplots(figsize=(8, 4))\n"
                      "ax.plot(x, y, marker='o', label='series A')\n"
                      "ax.plot(x, [v * 1.5 for v in y], label='series B')\n"
                      "ax.legend()\n"
                      "ax.grid(True)\n"
                      "fig.savefig('chart.png', dpi=150)   # no need to show\n"
                      "\n"
                      "# Bar chart:\n"
                      "plt.bar(['a', 'b', 'c'], [3, 7, 2])\n"
                      "\n"
                      "# Subplots:\n"
                      "fig, axes = plt.subplots(1, 2)\n"
                      "axes[0].plot(x, y)\n"
                      "axes[1].bar(['a', 'b'], [3, 7])"
        },
    ),
    new_task(
        'pandas_merge',
        [r'\bmerge\b.*\bdataframes?\b',
         r'\bpd\.merge\b',
         r'\bjoin\b.*\bdataframes?\b'],
        "Here's how to merge two DataFrames in pandas.",
        "pd.merge joins on columns (like SQL); how='left'/'inner'/'outer' controls which rows survive. DataFrame.join is a shortcut when merging on the index.",
        {
            'python': "import pandas as pd\n"
                      "\n"
                      "users = pd.DataFrame({'id': [1, 2, 3], 'name': ['a', 'b', 'c']})\n"
                      "orders = pd.DataFrame({'user_id': [1, 2, 4], 'total': [10, 20, 30]})\n"
                      "\n"
                      "# Inner join on a key column:\n"
                      "merged = pd.merge(users, orders, left_on='id', right_on='user_id')\n"
                      "\n"
                      "# Left join (keep every user):\n"
                      "merged = pd.merge(users, orders, left_on='id', right_on='user_id', how='left')\n"
                      "\n"
                      "# Outer join:\n"
                      "merged = pd.merge(users, orders, left_on='id', right_on='user_id', how='outer')\n"
                      "\n"
                      "# Same column name on both sides:\n"
                      "merged = pd.merge(users, orders, on='id')\n"
                      "\n"
                      "# Join on the index:\n"
                      "users.set_index('id').join(orders.set_index('user_id'))\n"
                      "\n"
                      "# Suffixes for overlapping columns:\n"
                      "pd.merge(users, orders, on='id', suffixes=('_u', '_o'))"
        },
    ),
    new_task(
        'express_middleware',
        [r'\bexpress\b.*\bmiddleware\b',
         r'\bmiddleware\b.*\bexpress\b'],
        "Here's how to add middleware to an Express app.",
        "app.use() registers middleware that runs for every request; a custom middleware is just a function(req, res, next). Order matters — middleware runs in registration order.",
        {
            'javascript': "const express = require('express');\n"
                          "const app = express();\n"
                          "\n"
                          "// Built-in middleware:\n"
                          "app.use(express.json());          // parse JSON bodies\n"
                          "app.use(express.static('public')); // serve static files\n"
                          "\n"
                          "// Custom logging middleware:\n"
                          "app.use((req, res, next) => {\n"
                          "    console.log(`${req.method} ${req.url}`);\n"
                          "    next();   // pass control to the next handler\n"
                          "});\n"
                          "\n"
                          "// Path-scoped middleware:\n"
                          "app.use('/api', (req, res, next) => {\n"
                          "    // runs only for /api routes\n"
                          "    next();\n"
                          "});\n"
                          "\n"
                          "// Auth middleware:\n"
                          "function requireAuth(req, res, next) {\n"
                          "    if (!req.headers.authorization) {\n"
                          "        return res.status(401).json({ error: 'unauthorized' });\n"
                          "    }\n"
                          "    next();\n"
                          "}\n"
                          "app.use(requireAuth);\n"
                          "\n"
                          "// Error-handling middleware (4 args = error handler):\n"
                          "app.use((err, req, res, next) => {\n"
                          "    console.error(err);\n"
                          "    res.status(500).json({ error: 'server error' });\n"
                          "});"
        },
    ),
    new_task(
        'express_body',
        [r'\bexpress\b.*\b(?:request\s+body|body)\b',
         r'\b(?:read|parse|access)\b.*\b(?:request\s+)?body\b.*\bexpress\b'],
        "Here's how to read the request body in Express.",
        "express.json() parses JSON bodies into req.body; express.urlencoded() handles form data. Without it req.body is undefined in Express 4.15+.",
        {
            'javascript': "const express = require('express');\n"
                          "const app = express();\n"
                          "\n"
                          "app.use(express.json());            // JSON bodies -> req.body\n"
                          "app.use(express.urlencoded({ extended: true }));  // form bodies\n"
                          "\n"
                          "app.post('/api/users', (req, res) => {\n"
                          "    console.log(req.body);          // parsed object\n"
                          "    res.json({ received: req.body });\n"
                          "});\n"
                          "\n"
                          "// Query string is separate:\n"
                          "app.get('/api/search', (req, res) => {\n"
                          "    console.log(req.query.q);       // /api/search?q=hi -> 'hi'\n"
                          "    res.json({ q: req.query.q });\n"
                          "});\n"
                          "\n"
                          "// Route params:\n"
                          "app.get('/api/users/:id', (req, res) => {\n"
                          "    console.log(req.params.id);     // /api/users/42 -> '42'\n"
                          "    res.json({ id: req.params.id });\n"
                          "});"
        },
    ),
    new_task(
        'django_model',
        [r'\bdjango\b.*\bmodel\b',
         r'\bmodel\b.*\bdjango\b'],
        "Here's how to define a model in Django.",
        "Models are Python classes that map to database tables; fields become columns. After defining them run makemigrations + migrate. The Meta class controls ordering, table names, and constraints.",
        {
            'python': "# models.py\n"
                      "from django.db import models\n"
                      "\n"
                      "class Author(models.Model):\n"
                      "    name = models.CharField(max_length=100)\n"
                      "    email = models.EmailField(unique=True)\n"
                      "\n"
                      "    def __str__(self):\n"
                      "        return self.name\n"
                      "\n"
                      "\n"
                      "class Book(models.Model):\n"
                      "    title = models.CharField(max_length=200)\n"
                      "    author = models.ForeignKey(Author, on_delete=models.CASCADE,\n"
                      "                                related_name='books')\n"
                      "    pages = models.PositiveIntegerField(default=0)\n"
                      "    published = models.DateField(null=True, blank=True)\n"
                      "    created_at = models.DateTimeField(auto_now_add=True)\n"
                      "\n"
                      "    class Meta:\n"
                      "        ordering = ['title']\n"
                      "\n"
                      "    def __str__(self):\n"
                      "        return self.title\n"
                      "\n"
                      "# After editing: python manage.py makemigrations && migrate"
        },
    ),
    new_task(
        'fastapi_endpoint',
        [r'\bfastapi\b',
         r'\b(?:get|post|put|delete)\s+endpoint\b.*\b(?:python|fastapi)\b'],
        "Here's how to make a FastAPI endpoint.",
        "Decorators map functions to routes; type hints drive request parsing and validation via Pydantic. Run with uvicorn app:app --reload, and the interactive docs appear at /docs.",
        {
            'python': "from fastapi import FastAPI, HTTPException\n"
                      "from pydantic import BaseModel\n"
                      "\n"
                      "app = FastAPI()\n"
                      "\n"
                      "\n"
                      "class Item(BaseModel):\n"
                      "    name: str\n"
                      "    price: float\n"
                      "\n"
                      "\n"
                      "@app.get('/')\n"
                      "def root():\n"
                      "    return {'message': 'hello'}\n"
                      "\n"
                      "\n"
                      "@app.get('/items/{item_id}')\n"
                      "def get_item(item_id: int):\n"
                      "    if item_id != 1:\n"
                      "        raise HTTPException(status_code=404, detail='not found')\n"
                      "    return {'id': item_id, 'name': 'widget'}\n"
                      "\n"
                      "\n"
                      "@app.post('/items')\n"
                      "def create_item(item: Item):\n"
                      "    return {'ok': True, 'item': item}\n"
                      "\n"
                      "# Run: uvicorn main:app --reload   (docs at http://localhost:8000/docs)"
        },
    ),
    new_task(
        'sql_injection_prevent',
        [r'\bsql\s+injection\b'],
        "Here's how to prevent SQL injection in {lang}.",
        "Never interpolate values into SQL strings. Parameterized queries (placeholders) keep data separate from code — the database driver handles escaping. This is the single most important web-security habit.",
        {
            'python': "import sqlite3\n"
                      "\n"
                      "# WRONG — vulnerable to injection:\n"
                      "# cur.execute(f\"SELECT * FROM users WHERE name = '{name}'\")\n"
                      "\n"
                      "# RIGHT — parameterized query:\n"
                      "conn = sqlite3.connect('app.db')\n"
                      "cur = conn.cursor()\n"
                      "cur.execute('SELECT * FROM users WHERE name = ?', (name,))\n"
                      "cur.execute('INSERT INTO users (name) VALUES (?)', (name,))\n"
                      "\n"
                      "# psycopg2 (PostgreSQL) uses %s:\n"
                      "# cur.execute('SELECT * FROM users WHERE name = %s', (name,))\n"
                      "\n"
                      "# SQLAlchemy / ORMs parameterize automatically — use them.\n"
                      "\n"
                      "# For dynamic table/column names (can't parameterize),\n"
                      "# validate against an allowlist:\n"
                      "allowed = {'name', 'email'}\n"
                      "if column not in allowed:\n"
                      "    raise ValueError('bad column')",
            'javascript': "// WRONG — vulnerable:\n"
                          "// db.query(`SELECT * FROM users WHERE name = '${name}'`)\n"
                          "\n"
                          "// RIGHT — parameterized:\n"
                          "const { Pool } = require('pg');\n"
                          "const pool = new Pool();\n"
                          "await pool.query('SELECT * FROM users WHERE name = $1', [name]);\n"
                          "\n"
                          "// mysql2 uses ? placeholders:\n"
                          "// await db.query('SELECT * FROM users WHERE name = ?', [name]);\n"
                          "\n"
                          "// An ORM (Prisma, Sequelize, Knex) parameterizes for you.",
        },
    ),
    new_task(
        'password_hash',
        [r'\bhash\b.*\bpassword\b',
         r'\bpassword\b.*\b(?:hashing|hash|bcrypt)\b'],
        "Here's how to hash passwords safely in {lang}.",
        "Never use md5/sha1/sha256 for passwords — they're too fast. Use a key-derivation function with a per-password salt: bcrypt, argon2, or PBKDF2. Verify with the library's check function, never by re-hashing.",
        {
            'python': "# pip install bcrypt\n"
                      "import bcrypt\n"
                      "\n"
                      "password = b'supersecret'\n"
                      "\n"
                      "# Hash (generates and stores a random salt):\n"
                      "hashed = bcrypt.hashpw(password, bcrypt.gensalt())\n"
                      "print(hashed.decode())\n"
                      "\n"
                      "# Verify later:\n"
                      "if bcrypt.checkpw(password, hashed):\n"
                      "    print('ok')\n"
                      "\n"
                      "# Stdlib alternative — PBKDF2 with a salt:\n"
                      "import hashlib, os\n"
                      "salt = os.urandom(16)\n"
                      "dk = hashlib.pbkdf2_hmac('sha256', password, salt, 600_000)\n"
                      "stored = salt + dk   # keep both; verify by recomputing",
            'javascript': "// npm install bcryptjs\n"
                          "const bcrypt = require('bcryptjs');\n"
                          "\n"
                          "const password = 'supersecret';\n"
                          "\n"
                          "// Hash (includes a random salt):\n"
                          "const hashed = await bcrypt.hash(password, 12);\n"
                          "\n"
                          "// Verify:\n"
                          "const ok = await bcrypt.compare(password, hashed);\n"
                          "console.log(ok);   // true",
        },
    ),
    new_task(
        'encrypt_string',
        [r'\bencrypt\b.*\b(?:string|text|data|message)\b',
         r'\b(?:symmetric\s+)?encryption\b.*\b(?:python|string|data)\b'],
        "Here's how to encrypt a string in {lang}.",
        "For application data use authenticated symmetric encryption — Fernet (AES-128-CBC + HMAC) is the easy, safe choice. Store the key somewhere protected, never in the repo.",
        {
            'python': "# pip install cryptography\n"
                      "from cryptography.fernet import Fernet\n"
                      "\n"
                      "# Generate and save a key ONCE:\n"
                      "key = Fernet.generate_key()\n"
                      "print(key.decode())   # store this securely\n"
                      "\n"
                      "f = Fernet(key)\n"
                      "\n"
                      "# Encrypt:\n"
                      "token = f.encrypt(b'hello secret')\n"
                      "print(token)\n"
                      "\n"
                      "# Decrypt:\n"
                      "plaintext = f.decrypt(token)\n"
                      "print(plaintext.decode())   # hello secret\n"
                      "\n"
                      "# Wrong key / tampered token raises InvalidToken.",
            'javascript': "// Node.js built-in crypto (AES-256-GCM):\n"
                          "const crypto = require('crypto');\n"
                          "\n"
                          "const key = crypto.randomBytes(32);   // keep this secret\n"
                          "const iv = crypto.randomBytes(12);    // unique per message\n"
                          "\n"
                          "const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);\n"
                          "const encrypted = Buffer.concat([\n"
                          "    cipher.update('hello secret', 'utf8'),\n"
                          "    cipher.final(),\n"
                          "]);\n"
                          "const tag = cipher.getAuthTag();\n"
                          "console.log(encrypted.toString('base64'), tag.toString('base64'));",
        },
    ),
    new_task(
        'jwt_generate',
        [r'\bjwt\b',
         r'\bjson\s+web\s+token\b'],
        "Here's how to generate and verify a JWT in {lang}.",
        "A JWT is a signed token: header.payload.signature. Sign with a strong secret (HS256) or a private key (RS256). Set an expiry (exp) and always verify on the receiving side.",
        {
            'python': "# pip install pyjwt\n"
                      "import jwt\n"
                      "import datetime\n"
                      "\n"
                      "SECRET = 'change-me-to-a-long-random-secret'\n"
                      "\n"
                      "payload = {\n"
                      "    'sub': 'user-42',\n"
                      "    'role': 'admin',\n"
                      "    'exp': datetime.datetime.now(datetime.timezone.utc)\n"
                      "           + datetime.timedelta(hours=1),\n"
                      "}\n"
                      "\n"
                      "# Generate:\n"
                      "token = jwt.encode(payload, SECRET, algorithm='HS256')\n"
                      "print(token)\n"
                      "\n"
                      "# Verify (raises on bad signature / expired):\n"
                      "try:\n"
                      "    decoded = jwt.decode(token, SECRET, algorithms=['HS256'])\n"
                      "    print(decoded['sub'])\n"
                      "except jwt.ExpiredSignatureError:\n"
                      "    print('token expired')\n"
                      "except jwt.InvalidTokenError:\n"
                      "    print('invalid token')",
            'javascript': "// npm install jsonwebtoken\n"
                          "const jwt = require('jsonwebtoken');\n"
                          "\n"
                          "const SECRET = 'change-me-to-a-long-random-secret';\n"
                          "\n"
                          "// Generate:\n"
                          "const token = jwt.sign(\n"
                          "    { sub: 'user-42', role: 'admin' },\n"
                          "    SECRET,\n"
                          "    { expiresIn: '1h' }\n"
                          ");\n"
                          "\n"
                          "// Verify:\n"
                          "try {\n"
                          "    const decoded = jwt.verify(token, SECRET);\n"
                          "    console.log(decoded.sub);\n"
                          "} catch (err) {\n"
                          "    console.error('invalid or expired:', err.message);\n"
                          "}",
        },
    ),
    new_task(
        'best_time_stock',
        [r'\bbest\s+time\b.*\b(?:buy|sell)\b',
         r'\bmax\s+profit\b.*\b(?:stock|prices?)\b'],
        "Here's a {lang} function that finds the best day to buy and sell stock.",
        "Track the lowest price seen so far and the best profit at each step — one pass, O(n). The naive double loop is O(n²) and times out on large inputs.",
        {
            'python': "def max_profit(prices: list) -> int:\n"
                      "    \"\"\"Max profit from one buy then one sell.\"\"\"\n"
                      "    min_price = float('inf')\n"
                      "    best = 0\n"
                      "    for price in prices:\n"
                      "        if price < min_price:\n"
                      "            min_price = price\n"
                      "        elif price - min_price > best:\n"
                      "            best = price - min_price\n"
                      "    return best\n"
                      "\n"
                      "# Examples:\n"
                      "print(max_profit([7, 1, 5, 3, 6, 4]))   # 5 (buy 1, sell 6)\n"
                      "print(max_profit([7, 6, 4, 3, 1]))      # 0 (never profitable)",
            'javascript': "function maxProfit(prices) {\n"
                          "    let minPrice = Infinity;\n"
                          "    let best = 0;\n"
                          "    for (const price of prices) {\n"
                          "        if (price < minPrice) minPrice = price;\n"
                          "        else best = Math.max(best, price - minPrice);\n"
                          "    }\n"
                          "    return best;\n"
                          "}\n"
                          "\n"
                          "console.log(maxProfit([7, 1, 5, 3, 6, 4]));  // 5",
        },
    ),
    new_task(
        'product_except_self',
        [r'\bproduct\s+of\s+array\s+except\s+self\b',
         r'\bproduct\s+except\s+self\b'],
        "Here's a {lang} function that computes the product of an array except itself.",
        "Two passes build prefix and suffix products; the answer at each index is prefix[i] * suffix[i]. This avoids division (so zeros are safe) and runs in O(n) time, O(n) space (O(1) with an output array).",
        {
            'python': "def product_except_self(nums: list) -> list:\n"
                      "    n = len(nums)\n"
                      "    out = [1] * n\n"
                      "    prefix = 1\n"
                      "    for i in range(n):\n"
                      "        out[i] = prefix\n"
                      "        prefix *= nums[i]\n"
                      "    suffix = 1\n"
                      "    for i in range(n - 1, -1, -1):\n"
                      "        out[i] *= suffix\n"
                      "        suffix *= nums[i]\n"
                      "    return out\n"
                      "\n"
                      "print(product_except_self([1, 2, 3, 4]))   # [24, 12, 8, 6]",
            'javascript': "function productExceptSelf(nums) {\n"
                          "    const n = nums.length;\n"
                          "    const out = new Array(n).fill(1);\n"
                          "    let prefix = 1;\n"
                          "    for (let i = 0; i < n; i++) {\n"
                          "        out[i] = prefix;\n"
                          "        prefix *= nums[i];\n"
                          "    }\n"
                          "    let suffix = 1;\n"
                          "    for (let i = n - 1; i >= 0; i--) {\n"
                          "        out[i] *= suffix;\n"
                          "        suffix *= nums[i];\n"
                          "    }\n"
                          "    return out;\n"
                          "}\n"
                          "console.log(productExceptSelf([1, 2, 3, 4]));  // [24, 12, 8, 6]",
        },
    ),
    new_task(
        'group_anagrams',
        [r'\bgroup\s+anagrams\b',
         r'\banagrams?\b.*\bgroup\b'],
        "Here's a {lang} function that groups anagrams together.",
        "Sort each word (or use a character-count tuple) as the group key — anagrams produce identical keys. A dict/Map collects the groups in one pass.",
        {
            'python': "from collections import defaultdict\n"
                      "\n"
                      "def group_anagrams(words: list) -> list:\n"
                      "    groups = defaultdict(list)\n"
                      "    for word in words:\n"
                      "        key = ''.join(sorted(word))\n"
                      "        groups[key].append(word)\n"
                      "    return list(groups.values())\n"
                      "\n"
                      "# Example:\n"
                      "print(group_anagrams(['eat', 'tea', 'tan', 'ate', 'nat', 'bat']))\n"
                      "# [['eat', 'tea', 'ate'], ['tan', 'nat'], ['bat']]",
            'javascript': "function groupAnagrams(words) {\n"
                          "    const groups = new Map();\n"
                          "    for (const word of words) {\n"
                          "        const key = [...word].sort().join('');\n"
                          "        (groups.get(key) || groups.set(key, []).get(key)).push(word);\n"
                          "    }\n"
                          "    return [...groups.values()];\n"
                          "}\n"
                          "\n"
                          "console.log(groupAnagrams(['eat', 'tea', 'tan', 'ate', 'nat', 'bat']));",
        },
    ),
    new_task(
        'kth_largest',
        [r'\bkth\s+largest\b',
         r'\b(?:kth|k-th)\s+biggest\b'],
        "Here's a {lang} function that finds the kth largest element in a list.",
        "sort + index is clearest; heapq.nlargest is O(n log k). For a full solution to the classic problem, a min-heap of size k or quickselect gives O(n) average.",
        {
            'python': "import heapq\n"
                      "\n"
                      "def kth_largest(nums: list, k: int) -> int:\n"
                      "    \"\"\"kth largest (1-based: k=1 is the largest).\"\"\"\n"
                      "    return heapq.nlargest(k, nums)[-1]\n"
                      "\n"
                      "# Sort + index (simplest):\n"
                      "def kth_largest_sorted(nums: list, k: int) -> int:\n"
                      "    return sorted(nums, reverse=True)[k - 1]\n"
                      "\n"
                      "# Min-heap of size k:\n"
                      "def kth_largest_heap(nums: list, k: int) -> int:\n"
                      "    heap = nums[:k]\n"
                      "    heapq.heapify(heap)\n"
                      "    for x in nums[k:]:\n"
                      "        if x > heap[0]:\n"
                      "            heapq.heapreplace(heap, x)\n"
                      "    return heap[0]\n"
                      "\n"
                      "print(kth_largest([3, 2, 1, 5, 6, 4], 2))   # 5",
            'javascript': "function kthLargest(nums, k) {\n"
                          "    return [...nums].sort((a, b) => b - a)[k - 1];\n"
                          "}\n"
                          "\n"
                          "console.log(kthLargest([3, 2, 1, 5, 6, 4], 2));  // 5",
        },
    ),
    new_task(
        'plus_one',
        [r'\bplus\s+one\b'],
        "Here's a {lang} function for the 'plus one' problem.",
        "Add 1 to a number stored as an array of digits. Walk from the last digit, carrying a 1 forward; if the carry survives the front, prepend a 1.",
        {
            'python': "def plus_one(digits: list) -> list:\n"
                      "    \"\"\"Increment a number given as a list of digits.\"\"\"\n"
                      "    for i in range(len(digits) - 1, -1, -1):\n"
                      "        if digits[i] < 9:\n"
                      "            digits[i] += 1\n"
                      "            return digits\n"
                      "        digits[i] = 0\n"
                      "    return [1] + digits\n"
                      "\n"
                      "print(plus_one([1, 2, 3]))   # [1, 2, 4]\n"
                      "print(plus_one([9, 9, 9]))   # [1, 0, 0, 0]",
            'javascript': "function plusOne(digits) {\n"
                          "    for (let i = digits.length - 1; i >= 0; i--) {\n"
                          "        if (digits[i] < 9) {\n"
                          "            digits[i]++;\n"
                          "            return digits;\n"
                          "        }\n"
                          "        digits[i] = 0;\n"
                          "    }\n"
                          "    return [1, ...digits];\n"
                          "}\n"
                          "console.log(plusOne([1, 2, 3]));   // [1, 2, 4]",
        },
    ),
    new_task(
        'move_zeroes',
        [r'\bmove\s+zeroes?\b',
         r'\bmove\s+zeros?\s+to\s+(?:the\s+)?end\b'],
        "Here's a {lang} function that moves zeroes to the end of an array.",
        "Use a write pointer: copy every non-zero forward, then fill the tail with zeros. One pass, in place, preserves relative order.",
        {
            'python': "def move_zeroes(nums: list) -> None:\n"
                      "    \"\"\"Move all 0s to the end, keeping other elements' order.\"\"\"\n"
                      "    write = 0\n"
                      "    for read, x in enumerate(nums):\n"
                      "        if x != 0:\n"
                      "            nums[write] = x\n"
                      "            write += 1\n"
                      "    for i in range(write, len(nums)):\n"
                      "        nums[i] = 0\n"
                      "\n"
                      "nums = [0, 1, 0, 3, 12]\n"
                      "move_zeroes(nums)\n"
                      "print(nums)   # [1, 3, 12, 0, 0]",
            'javascript': "function moveZeroes(nums) {\n"
                          "    let write = 0;\n"
                          "    for (let read = 0; read < nums.length; read++) {\n"
                          "        if (nums[read] !== 0) nums[write++] = nums[read];\n"
                          "    }\n"
                          "    for (let i = write; i < nums.length; i++) nums[i] = 0;\n"
                          "}\n"
                          "const nums = [0, 1, 0, 3, 12];\n"
                          "moveZeroes(nums);\n"
                          "console.log(nums);   // [1, 3, 12, 0, 0]",
        },
    ),
    new_task(
        'valid_sudoku',
        [r'\bvalid\s+sudoku\b'],
        "Here's a {lang} function that checks whether a Sudoku board is valid.",
        "Validate rows, columns, and 3x3 boxes with sets, tracking each digit once. Only filled cells matter — '.' cells are skipped. Empty cells never invalidate a board.",
        {
            'python': "def is_valid_sudoku(board: list) -> bool:\n"
                      "    \"\"\"board: 9x9 of '1'-'9' or '.'.\"\"\"\n"
                      "    rows = [set() for _ in range(9)]\n"
                      "    cols = [set() for _ in range(9)]\n"
                      "    boxes = [set() for _ in range(9)]\n"
                      "    for r in range(9):\n"
                      "        for c in range(9):\n"
                      "            v = board[r][c]\n"
                      "            if v == '.':\n"
                      "                continue\n"
                      "            b = (r // 3) * 3 + c // 3\n"
                      "            if v in rows[r] or v in cols[c] or v in boxes[b]:\n"
                      "                return False\n"
                      "            rows[r].add(v)\n"
                      "            cols[c].add(v)\n"
                      "            boxes[b].add(v)\n"
                      "    return True",
            'javascript': "function isValidSudoku(board) {\n"
                          "    const rows = Array.from({ length: 9 }, () => new Set());\n"
                          "    const cols = Array.from({ length: 9 }, () => new Set());\n"
                          "    const boxes = Array.from({ length: 9 }, () => new Set());\n"
                          "    for (let r = 0; r < 9; r++) {\n"
                          "        for (let c = 0; c < 9; c++) {\n"
                          "            const v = board[r][c];\n"
                          "            if (v === '.') continue;\n"
                          "            const b = Math.floor(r / 3) * 3 + Math.floor(c / 3);\n"
                          "            if (rows[r].has(v) || cols[c].has(v) || boxes[b].has(v)) return false;\n"
                          "            rows[r].add(v); cols[c].add(v); boxes[b].add(v);\n"
                          "        }\n"
                          "    }\n"
                          "    return true;\n"
                          "}",
        },
    ),
    new_task(
        'python_generator',
        [r'\b(?:write|create|use)\b.*\bgenerator\b',
         r'\byield\b.*\b(?:generator|function)\b'],
        "Here's how to write a generator in {lang}.",
        "A function with yield is a generator: it produces values lazily, one at a time, keeping its state between calls. Use them for streams, infinite sequences, and memory-friendly iteration.",
        {
            'python': "def countdown(n: int):\n"
                      "    while n > 0:\n"
                      "        yield n\n"
                      "        n -= 1\n"
                      "\n"
                      "for x in countdown(3):\n"
                      "    print(x)      # 3, 2, 1\n"
                      "\n"
                      "# Infinite sequence (lazy):\n"
                      "def fib():\n"
                      "    a, b = 0, 1\n"
                      "    while True:\n"
                      "        yield a\n"
                      "        a, b = b, a + b\n"
                      "\n"
                      "f = fib()\n"
                      "print([next(f) for _ in range(8)])   # [0, 1, 1, 2, 3, 5, 8, 13]\n"
                      "\n"
                      "# Generator expressions:\n"
                      "total = sum(x * x for x in range(1000))\n"
                      "\n"
                      "# Memory-friendly file lines:\n"
                      "def lines(filename):\n"
                      "    with open(filename, encoding='utf-8') as fh:\n"
                      "        for line in fh:\n"
                      "            yield line.rstrip()",
            'javascript': "// Generators use function* and yield:\n"
                          "function* countdown(n) {\n"
                          "    while (n > 0) yield n--;\n"
                          "}\n"
                          "\n"
                          "for (const x of countdown(3)) console.log(x);   // 3, 2, 1\n"
                          "\n"
                          "// Infinite sequence:\n"
                          "function* fib() {\n"
                          "    let [a, b] = [0, 1];\n"
                          "    while (true) {\n"
                          "        yield a;\n"
                          "        [a, b] = [b, a + b];\n"
                          "    }\n"
                          "}\n"
                          "const f = fib();\n"
                          "console.log([...Array(8)].map(() => f.next().value));\n"
                          "// [0, 1, 1, 2, 3, 5, 8, 13]",
        },
    ),
    new_task(
        'dataclass',
        [r'\bdataclass\b'],
        "Here's how to define a dataclass in {lang}.",
        "@dataclass auto-generates __init__, __repr__, and __eq__ from type-annotated fields. frozen=True makes instances immutable; field(default_factory=...) handles mutable defaults safely.",
        {
            'python': "from dataclasses import dataclass, field\n"
                      "\n"
                      "@dataclass\n"
                      "class Point:\n"
                      "    x: float\n"
                      "    y: float\n"
                      "\n"
                      "@dataclass\n"
                      "class User:\n"
                      "    name: str\n"
                      "    email: str\n"
                      "    active: bool = True\n"
                      "    tags: list = field(default_factory=list)   # never []!\n"
                      "\n"
                      "u = User('alice', 'a@example.com')\n"
                      "print(u)                  # User(name='alice', email='a@example.com', active=True, tags=[])\n"
                      "print(u == User('alice', 'a@example.com'))   # True (auto __eq__)\n"
                      "\n"
                      "# Immutable:\n"
                      "@dataclass(frozen=True)\n"
                      "class Config:\n"
                      "    host: str\n"
                      "    port: int\n"
                      "\n"
                      "# Ordered + comparable:\n"
                      "@dataclass(order=True)\n"
                      "class Score:\n"
                      "    value: int",
        },
    ),
    new_task(
        'context_manager',
        [r'\bcontext\s+manager\b',
         r'\b(?:write|create|use)\b.*\bwith\s+statement\b'],
        "Here's how to write a context manager in {lang}.",
        "A class with __enter__/__exit__ (or @contextmanager + yield) defines setup/teardown for `with` blocks — perfect for connections, locks, and temporary state. __exit__ always runs, even on exceptions.",
        {
            'python': "from contextlib import contextmanager\n\n"
                      "# Class-based:\n"
                      "class Timer:\n"
                      "    def __enter__(self):\n"
                      "        import time\n"
                      "        self.start = time.perf_counter()\n"
                      "        return self\n"
                      "    def __exit__(self, exc_type, exc, tb):\n"
                      "        import time\n"
                      "        print(f'took {time.perf_counter() - self.start:.3f}s')\n"
                      "        return False   # propagate exceptions\n"
                      "\n"
                      "with Timer():\n"
                      "    sum(range(1_000_000))\n"
                      "\n"
                      "# @contextmanager (simpler):\n"
                      "@contextmanager\n"
                      "def timer():\n"
                      "    import time\n"
                      "    start = time.perf_counter()\n"
                      "    try:\n"
                      "        yield\n"
                      "    finally:\n"
                      "        print(f'took {time.perf_counter() - start:.3f}s')\n"
                      "\n"
                      "with timer():\n"
                      "    sum(range(1_000_000))\n"
                      "\n"
                      "# Real-world use: connections, locks, temp dirs\n"
                      "import tempfile\n"
                      "with tempfile.TemporaryDirectory() as tmp:\n"
                      "    print(tmp)   # cleaned up automatically",
        },
    ),
    new_task(
        'fstring_padding',
        [r'\bf[- ]strings?\b.*\b(?:pad|padding|width|align|format)\b',
         r'\b(?:pad|padding|align)\b.*\bf[- ]strings?\b'],
        "Here's how to pad and align text with f-strings in {lang}.",
        "Format spec mini-language: {value:width} right-aligns, {value:<width} left-aligns, {value:^width} centers, and {value:0width} zero-pads numbers. Add precision with .2f.",
        {
            'python': "name = 'alice'\n"
                      "score = 42.567\n"
                      "\n"
                      "print(f'{name:>10}')      # '     alice'  (right align)\n"
                      "print(f'{name:<10}')      # 'alice     '  (left align)\n"
                      "print(f'{name:^10}')      # '  alice   '  (center)\n"
                      "\n"
                      "# Zero-pad numbers:\n"
                      "print(f'{7:03d}')         # '007'\n"
                      "print(f'{42:05d}')        # '00042'\n"
                      "\n"
                      "# Fill character + alignment:\n"
                      "print(f'{name:*^10}')     # '**alice***'\n"
                      "print(f'{name:.>10}')     # '.....alice'\n"
                      "\n"
                      "# Precision:\n"
                      "print(f'{score:.2f}')     # '42.57'\n"
                      "print(f'{score:10.2f}')   # '     42.57'\n"
                      "\n"
                      "# Table columns:\n"
                      "for n, s in [('alice', 95), ('bob', 100), ('carol', 87)]:\n"
                      "    print(f'{n:<8}{s:>3}')\n"
                      "# alice      95\n"
                      "# bob       100\n"
                      "# carol      87",
            'javascript': "// padStart / padEnd:\n"
                          "const name = 'alice';\n"
                          "console.log(name.padStart(10));   // '     alice'\n"
                          "console.log(name.padEnd(10));     // 'alice     '\n"
                          "console.log(name.padStart(10, '*'));  // '*****alice'\n"
                          "\n"
                          "// Zero-pad numbers:\n"
                          "console.log(String(7).padStart(3, '0'));    // '007'\n"
                          "console.log((42).toString().padStart(5, '0')); // '00042'\n"
                          "\n"
                          "// Decimal places (toFixed returns a string):\n"
                          "console.log((42.567).toFixed(2));   // '42.57'\n"
                          "console.log((42.567).toFixed(2).padStart(10));  // '     42.57'\n"
                          "\n"
                          "// Table columns:\n"
                          "for (const [n, s] of [['alice', 95], ['bob', 100], ['carol', 87]]) {\n"
                          "    console.log(n.padEnd(8) + String(s).padStart(3));\n"
                          "}",
        },
    ),
]
# kth_largest must sort BEFORE largest_number; group_anagrams before anagram(03)
largest_idx = next(i for i, t in enumerate(d13) if t['task'] == 'largest_number')
for t in reversed(new13):
    d13.insert(largest_idx, t)
save('13_python_utils.json', d13)

# ── 14_js_utils.json: js advanced ──────────────────────────────────────────
d14 = load('14_js_utils.json')
d14.append(new_task(
    'js_destructuring',
    [r'\bdestructuring\b',
     r'\bdestructure\b'],
    "Here's how to use destructuring in {lang}.",
    "Destructuring unpacks arrays and objects into variables in one statement. Use defaults, renaming, and rest (...) to handle partial data cleanly.",
    {
        'javascript': "// Array destructuring:\n"
                      "const [first, second, ...rest] = [1, 2, 3, 4, 5];\n"
                      "console.log(first, second, rest);   // 1 2 [3, 4, 5]\n"
                      "\n"
                      "// Skip elements:\n"
                      "const [, , third] = ['a', 'b', 'c'];\n"
                      "\n"
                      "// Swap:\n"
                      "let a = 1, b = 2;\n"
                      "[a, b] = [b, a];\n"
                      "\n"
                      "// Object destructuring:\n"
                      "const user = { name: 'alice', age: 30, city: 'Berlin' };\n"
                      "const { name, age } = user;\n"
                      "\n"
                      "// Rename + default:\n"
                      "const { name: userName, email = 'none' } = user;\n"
                      "\n"
                      "// Nested:\n"
                      "const { address: { street } } = { address: { street: 'Main 1' } };\n"
                      "\n"
                      "// Function params:\n"
                      "function greet({ name, age = 0 }) {\n"
                      "    console.log(`${name} is ${age}`);\n"
                      "}\n"
                      "greet(user);",
        'python': "# Tuple unpacking:\n"
                  "first, second, *rest = [1, 2, 3, 4, 5]\n"
                  "print(first, second, rest)   # 1 2 [3, 4, 5]\n"
                  "\n"
                  "# Swap:\n"
                  "a, b = b, a\n"
                  "\n"
                  "# Dict unpacking (**):\n"
                  "user = {'name': 'alice', 'age': 30}\n"
                  "copy = {**user, 'city': 'Berlin'}\n"
                  "\n"
                  "# Function kwargs:\n"
                  "def greet(name, age=0):\n"
                  "    print(f'{name} is {age}')\n"
                  "greet(**user)",
    },
))
d14.append(new_task(
    'optional_chaining',
    [r'\boptional\s+chaining\b'],
    "Here's how to use optional chaining in {lang}.",
    "?. short-circuits to undefined instead of throwing when the left side is null/undefined. Use it for nested access on data that may be missing; ?? provides a default for nullish values.",
    {
        'javascript': "const user = { profile: { name: 'alice' } };\n"
                      "\n"
                      "// Without optional chaining:\n"
                      "// const name = user.profile.name;  // throws if profile is missing\n"
                      "\n"
                      "// With ?. — safe nested access:\n"
                      "const name = user?.profile?.name;\n"
                      "console.log(name);   // 'alice'\n"
                      "\n"
                      "const empty = {};\n"
                      "console.log(empty?.profile?.name);   // undefined (no throw)\n"
                      "\n"
                      "// Optional call:\n"
                      "user.save?.();   // only called if save exists\n"
                      "\n"
                      "// ?? nullish coalescing — default only for null/undefined:\n"
                      "const port = process.env.PORT ?? 8000;\n"
                      "const count = user?.orders?.length ?? 0;\n"
                      "\n"
                      "// Note: || treats 0, '', false as falsy; ?? does not.\n"
                      "console.log(0 ?? 'default');   // 0\n"
                      "console.log(0 || 'default');   // 'default'",
        'python': "# Python's equivalent: the walrus-free safe access pattern\n"
                  "user = {'profile': {'name': 'alice'}}\n"
                  "\n"
                  "name = user.get('profile', {}).get('name')\n"
                  "print(name)   # alice\n"
                  "\n"
                  "# Or use .get with a chain:\n"
                  "name = (user.get('profile') or {}).get('name')\n"
                  "\n"
                  "# For attribute access:\n"
                  "class Box:\n"
                  "    def __init__(self, val=None):\n"
                  "        self.val = val\n"
                  "\n"
                  "b = Box()\n"
                  "value = getattr(b, 'val', None)\n"
                  "\n"
                  "# Modern alternative: try/except or the 'dotted' library.\n"
                  "try:\n"
                  "    name = user['profile']['name']\n"
                  "except KeyError:\n"
                  "    name = None",
    },
))
d14.append(new_task(
    'template_literals',
    [r'\btemplate\s+literals?\b',
     r'\b(?:backtick|template)\\s+strings?\b'],
    "Here's how to use template literals in {lang}.",
    "Backticks create strings that interpolate ${expr} and span multiple lines. Tagged templates (the function before the backtick) let you transform the parts programmatically.",
    {
        'javascript': "const name = 'alice';\n"
                      "const age = 30;\n"
                      "\n"
                      "// Interpolation:\n"
                      "const msg = `${name} is ${age} years old`;\n"
                      "console.log(msg);\n"
                      "\n"
                      "// Multi-line (no \\n needed):\n"
                      "const html = `\n"
                      "  <div>\n"
                      "    <h1>${name}</h1>\n"
                      "  </div>\n"
                      "`;\n"
                      "\n"
                      "// Expressions inside ${}:\n"
                      "console.log(`total: ${2 + 3}`);\n"
                      "console.log(`status: ${age >= 18 ? 'adult' : 'minor'}`);\n"
                      "\n"
                      "// Nested template literals:\n"
                      "const items = ['a', 'b'];\n"
                      "const list = `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul>`;\n"
                      "\n"
                      "// Tagged template:\n"
                      "function upper(strings, ...values) {\n"
                      "    return strings.reduce((out, s, i) => out + s + (values[i] ?? '').toString().toUpperCase(), '');\n"
                      "}\n"
                      "console.log(upper`hello ${name}`);   // hello ALICE",
        'python': "# f-strings are Python's template literals:\n"
                  "name = 'alice'\n"
                  "age = 30\n"
                  "\n"
                  "msg = f'{name} is {age} years old'\n"
                  "print(msg)\n"
                  "\n"
                  "# Multi-line:\n"
                  "html = f'''\n"
                  "<div>\n"
                  "  <h1>{name}</h1>\n"
                  "</div>\n"
                  "'''\n"
                  "\n"
                  "# Expressions:\n"
                  "print(f'total: {2 + 3}')\n"
                  "print(f'status: {\"adult\" if age >= 18 else \"minor\"}')\n"
                  "\n"
                  "# Format spec inside:\n"
                  "print(f'{age:03d}')    # 030",
    },
))
d14.append(new_task(
    'js_class_getters',
    [r'\bgetters?\b.*\b(?:class|object)\b',
     r'\bclass\b.*\bgetters?\b'],
    "Here's how to define getters in a JavaScript class.",
    "The get keyword defines a computed property that runs code on access — no parentheses needed. setters run on assignment. This is how you expose derived state cleanly.",
    {
        'javascript': "class Circle {\n"
                      "    constructor(radius) {\n"
                      "        this.radius = radius;\n"
                      "    }\n"
                      "\n"
                      "    get area() {\n"
                      "        return Math.PI * this.radius ** 2;\n"
                      "    }\n"
                      "\n"
                      "    get diameter() {\n"
                      "        return this.radius * 2;\n"
                      "    }\n"
                      "\n"
                      "    set diameter(d) {\n"
                      "        this.radius = d / 2;\n"
                      "    }\n"
                      "}\n"
                      "\n"
                      "const c = new Circle(5);\n"
                      "console.log(c.area);        // 78.5...  (no ()!)\n"
                      "c.diameter = 20;            // setter runs\n"
                      "console.log(c.radius);      // 10\n"
                      "\n"
                      "// Object literal getters:\n"
                      "const user = {\n"
                      "    first: 'alice',\n"
                      "    last: 'smith',\n"
                      "    get full() {\n"
                      "        return `${this.first} ${this.last}`;\n"
                      "    },\n"
                      "};\n"
                      "console.log(user.full);   // 'alice smith'",
        'python': "# Python's @property is the equivalent:\n"
                  "import math\n"
                  "\n"
                  "class Circle:\n"
                  "    def __init__(self, radius):\n"
                  "        self.radius = radius\n"
                  "\n"
                  "    @property\n"
                  "    def area(self):\n"
                  "        return math.pi * self.radius ** 2\n"
                  "\n"
                  "    @property\n"
                  "    def diameter(self):\n"
                  "        return self.radius * 2\n"
                  "\n"
                  "    @diameter.setter\n"
                  "    def diameter(self, d):\n"
                  "        self.radius = d / 2\n"
                  "\n"
                  "c = Circle(5)\n"
                  "print(c.area)     # 78.5...\n"
                  "c.diameter = 20\n"
                  "print(c.radius)   # 10",
    },
))
save('14_js_utils.json', d14)

# ── 11_git_bash.json: git tasks ────────────────────────────────────────────
d11b = load('11_git_bash.json')
d11b['tasks'].append(new_task(
    'git_rebase',
    [r'\brebase\b'],
    "Here's how to rebase a branch onto main in git.",
    "Rebasing replays your commits on top of another branch, giving a linear history. Only rebase commits you haven't pushed. Abort anytime with git rebase --abort.",
    {
        'bash': "# Switch to your feature branch:\n"
                "git checkout feature-branch\n"
                "\n"
                "# Replay its commits onto main:\n"
                "git rebase main\n"
                "\n"
                "# If conflicts occur, resolve them, then:\n"
                "git add <resolved-files>\n"
                "git rebase --continue\n"
                "\n"
                "# Or bail out entirely:\n"
                "git rebase --abort\n"
                "\n"
                "# One-liner from main:\n"
                "git checkout main && git pull && git checkout feature-branch && git rebase main\n"
                "\n"
                "# Interactive rebase (squash/reword/reorder):\n"
                "git rebase -i HEAD~3\n"
                "\n"
                "# After rebasing a pushed branch, force-push:\n"
                "git push --force-with-lease"
    },
    default_lang='bash',
))
d11b['tasks'].append(new_task(
    'git_cherry_pick',
    [r'\bcherry[- ]?pick\b'],
    "Here's how to cherry-pick a commit in git.",
    "cherry-pick applies one commit's changes onto your current branch — useful for moving a hotfix without merging the whole branch. Copy the commit hash from git log.",
    {
        'bash': "# Find the commit hash:\n"
                "git log --oneline -10\n"
                "\n"
                "# Apply it to the current branch:\n"
                "git cherry-pick a1b2c3d\n"
                "\n"
                "# Cherry-pick without committing yet:\n"
                "git cherry-pick -n a1b2c3d\n"
                "\n"
                "# Multiple commits in order:\n"
                "git cherry-pick a1b2c3d e4f5a6b\n"
                "\n"
                "# A range of commits:\n"
                "git cherry-pick a1b2c3d..e4f5a6b\n"
                "\n"
                "# If it conflicts, resolve, git add, then:\n"
                "git cherry-pick --continue\n"
                "\n"
                "# Or abandon the operation:\n"
                "git cherry-pick --abort"
    },
    default_lang='bash',
))
d11b['tasks'].append(new_task(
    'git_merge_conflict',
    [r'\bmerge\s+conflict\b',
     r'\bresolve\b.*\b(?:merge\s+)?conflict\b'],
    "Here's how to resolve a merge conflict in git.",
    "Conflicted files get conflict markers: <<<<<<< (yours), ======= (divider), >>>>>>> (theirs). Edit to the final content, git add, and commit. Use git mergetool for a visual diff.",
    {
        'bash': "# When a merge/rebase/pull reports conflicts:\n"
                "git status          # lists 'both modified' files\n"
                "\n"
                "# Open the file and resolve the markers:\n"
                "# <<<<<<< HEAD\n"
                "# your version\n"
                "# =======\n"
                "# their version\n"
                "# >>>>>>> feature-branch\n"
                "\n"
                "# Keep yours / theirs wholesale:\n"
                "git checkout --ours file.txt\n"
                "git checkout --theirs file.txt\n"
                "\n"
                "# After editing:\n"
                "git add file.txt\n"
                "git commit           # merge: creates the merge commit\n"
                "git rebase --continue  # if you were rebasing\n"
                "\n"
                "# Visual tool:\n"
                "git mergetool\n"
                "\n"
                "# Abort the whole merge:\n"
                "git merge --abort"
    },
    default_lang='bash',
))
d11b['tasks'].append(new_task(
    'git_amend',
    [r'\bamend\b'],
    "Here's how to amend the last commit in git.",
    "git commit --amend replaces the last commit's message (and can add staged changes). Only amend commits you haven't pushed — otherwise force-push with --force-with-lease.",
    {
        'bash': "# Change only the message:\n"
                "git commit --amend -m 'new message'\n"
                "\n"
                "# Add forgotten changes to the last commit:\n"
                "git add forgotten.py\n"
                "git commit --amend --no-edit    # keep the same message\n"
                "\n"
                "# Edit the message in your editor:\n"
                "git commit --amend\n"
                "\n"
                "# Author too:\n"
                "git commit --amend --author='alice <alice@example.com>'\n"
                "\n"
                "# If already pushed, force-push carefully:\n"
                "git push --force-with-lease"
    },
    default_lang='bash',
))
save('11_git_bash.json', d11b)

# ── 18_devops.json: ops + text tools ───────────────────────────────────────
d18 = load('18_devops.json')
d18.append(new_task(
    'kubectl_pods',
    [r'\bkubectl\b'],
    "Here's how to check pods with kubectl.",
    "kubectl get pods lists pods; add -n for a namespace, -o wide for node/IP, and -w to watch. Describe shows details and events; logs streams container output.",
    {
        'bash': "# List pods in the default namespace:\n"
                "kubectl get pods\n"
                "\n"
                "# In a specific namespace:\n"
                "kubectl get pods -n myapp\n"
                "\n"
                "# All namespaces:\n"
                "kubectl get pods -A\n"
                "\n"
                "# More detail:\n"
                "kubectl get pods -o wide\n"
                "\n"
                "# Watch for changes:\n"
                "kubectl get pods -w\n"
                "\n"
                "# Describe one pod (events, status):\n"
                "kubectl describe pod my-pod-abc123\n"
                "\n"
                "# Logs:\n"
                "kubectl logs my-pod-abc123\n"
                "kubectl logs deployment/my-app -f    # follow\n"
                "\n"
                "# Exec into a container:\n"
                "kubectl exec -it my-pod-abc123 -- /bin/sh"
    },
    default_lang='bash',
))
d18.append(new_task(
    'k8s_deployment',
    [r'\bkubernetes\b.*\bdeployment\b',
     r'\bk8s\b.*\bdeployment\b',
     r'\bdeployment\s+yaml\b'],
    "Here's a Kubernetes Deployment manifest.",
    "A Deployment manages replica Pods with rolling updates and self-healing. Apply with kubectl apply -f, scale with kubectl scale, and check rollout status with kubectl rollout status.",
    {
        'bash': "# deployment.yaml\n"
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: web\n"
                "  labels:\n"
                "    app: web\n"
                "spec:\n"
                "  replicas: 3\n"
                "  selector:\n"
                "    matchLabels:\n"
                "      app: web\n"
                "  template:\n"
                "    metadata:\n"
                "      labels:\n"
                "        app: web\n"
                "    spec:\n"
                "      containers:\n"
                "        - name: web\n"
                "          image: myapp:1.0.0\n"
                "          ports:\n"
                "            - containerPort: 8000\n"
                "          env:\n"
                "            - name: APP_ENV\n"
                "              value: production\n"
                "          resources:\n"
                "            requests:\n"
                "              cpu: 100m\n"
                "              memory: 128Mi\n"
                "            limits:\n"
                "              cpu: 500m\n"
                "              memory: 512Mi\n"
                "          readinessProbe:\n"
                "            httpGet:\n"
                "              path: /health\n"
                "              port: 8000\n"
                "\n"
                "# Apply:  kubectl apply -f deployment.yaml\n"
                "# Scale:  kubectl scale deployment web --replicas=5\n"
                "# Status: kubectl rollout status deployment/web\n"
                "# Update: kubectl set image deployment/web web=myapp:1.1.0\n"
                "# Rollback: kubectl rollout undo deployment/web"
    },
    default_lang='bash',
))
d18.append(new_task(
    'nginx_static',
    [r'\bnginx\b'],
    "Here's an nginx config that serves a static site.",
    "The server block maps a domain to a root directory; try_files enables SPA-style clean URLs. Enable compression and cache headers for performance. Test with nginx -t before reloading.",
    {
        'bash': "# /etc/nginx/sites-available/mysite\n"
                "server {\n"
                "    listen 80;\n"
                "    server_name example.com www.example.com;\n"
                "\n"
                "    root /var/www/mysite;\n"
                "    index index.html;\n"
                "\n"
                "    # Clean URLs for a single-page app:\n"
                "    location / {\n"
                "        try_files $uri $uri/ /index.html;\n"
                "    }\n"
                "\n"
                "    # Cache static assets:\n"
                "    location ~* \\.(css|js|png|jpg|svg|woff2)$ {\n"
                "        expires 30d;\n"
                "        add_header Cache-Control \"public\";\n"
                "    }\n"
                "\n"
                "    # Gzip:\n"
                "    gzip on;\n"
                "    gzip_types text/css application/javascript image/svg+xml;\n"
                "}\n"
                "\n"
                "# Enable it:\n"
                "#   sudo ln -s /etc/nginx/sites-available/mysite /etc/nginx/sites-enabled/\n"
                "#   sudo nginx -t          # test the config\n"
                "#   sudo systemctl reload nginx"
    },
    default_lang='bash',
))
d18.append(new_task(
    'docker_multi_stage',
    [r'\bmulti[- ]stage\b.*\b(?:build|docker)\b',
     r'\bdocker\b.*\bmulti[- ]stage\b'],
    "Here's a Docker multi-stage build.",
    "Multi-stage builds compile/build in one stage (with all the tooling) and copy only the artifacts into a slim final image — much smaller and safer. Each FROM starts a new stage; AS names it.",
    {
        'bash': "# Dockerfile — Go example:\n"
                "FROM golang:1.22 AS builder\n"
                "WORKDIR /src\n"
                "COPY go.mod go.sum ./\n"
                "RUN go mod download\n"
                "COPY . .\n"
                "RUN CGO_ENABLED=0 go build -o /app ./cmd/server\n"
                "\n"
                "# Final stage: just the binary\n"
                "FROM scratch\n"
                "COPY --from=builder /app /app\n"
                "EXPOSE 8080\n"
                "ENTRYPOINT [\"/app\"]\n"
                "\n"
                "# Python example:\n"
                "# FROM python:3.12-slim AS build\n"
                "#   ... pip install --prefix=/install -r requirements.txt\n"
                "# FROM python:3.12-slim\n"
                "# COPY --from=build /install /usr/local\n"
                "#   ... copy app code, CMD ...\n"
                "\n"
                "# Build: docker build -t myapp .\n"
                "# Inspect stages: docker build --target builder -t myapp-builder ."
    },
    default_lang='bash',
))
d18.append(new_task(
    'awk_column',
    [r'\bawk\b'],
    "Here's how to extract a column from a file with awk.",
    "awk splits each line into fields: $1, $2, ... (FS default is whitespace). Set -F for a delimiter like a comma. Print with printf for aligned output.",
    {
        'bash': "# Print the second column (whitespace-separated):\n"
                "awk '{print $2}' data.txt\n"
                "\n"
                "# CSV with -F:\n"
                "awk -F, '{print $2}' data.csv\n"
                "\n"
                "# Header + first two columns:\n"
                "awk -F, 'NR==1 || NR>1 {print $1, $2}' data.csv\n"
                "\n"
                "# Skip the header entirely:\n"
                "awk -F, 'NR>1 {print $2}' data.csv\n"
                "\n"
                "# Filter + column:\n"
                "awk -F, '$3 > 100 {print $1}' data.csv\n"
                "\n"
                "# Sum a column:\n"
                "awk -F, '{sum += $2} END {print sum}' data.csv\n"
                "\n"
                "# Formatted output:\n"
                "awk '{printf \"%-10s %5d\\n\", $1, $2}' data.txt"
    },
    default_lang='bash',
))
d18.append(new_task(
    'jq_parse',
    [r'\bjq\b'],
    "Here's how to parse JSON in bash with jq.",
    "jq filters JSON: .field, .[index], .[] iterates, | pipes filters. Combine with curl for API output. Use -r for raw strings (no quotes).",
    {
        'bash': "# Pretty-print:\n"
                "cat data.json | jq .\n"
                "curl -s https://api.example.com/data | jq .\n"
                "\n"
                "# Extract a field:\n"
                "echo '{\"name\": \"alice\", \"age\": 30}' | jq '.name'\n"
                "# \"alice\"  (with -r: alice)\n"
                "\n"
                "# Array element / iteration:\n"
                "jq '.[0]' data.json        # first element\n"
                "jq '.[].name' data.json    # name of each element\n"
                "\n"
                "# Filtering:\n"
                "jq '.[] | select(.age > 21)' data.json\n"
                "\n"
                "# Transform:\n"
                "jq '{users: [.[] | {n: .name, a: .age}]}' data.json\n"
                "\n"
                "# Length / counts:\n"
                "jq 'length' data.json\n"
                "\n"
                "# Key lookup with default:\n"
                "jq '.missing // \"fallback\"' data.json"
    },
    default_lang='bash',
))
d18.append(new_task(
    'xargs_parallel',
    [r'\bxargs\b'],
    "Here's how to run commands in parallel with xargs.",
    "xargs builds commands from stdin. -P sets parallelism, -n batches arguments, -0 handles newlines in filenames safely (pair with find -print0).",
    {
        'bash': "# Run one command per line, 4 at a time:\n"
                "cat urls.txt | xargs -P 4 -I {} curl -s {} -o /dev/null\n"
                "\n"
                "# Process files, 4 in parallel:\n"
                "find . -name '*.jpg' -print0 | xargs -0 -P 4 -n 1 sh -c 'convert \"$0\" \"${0%.jpg}.png\"'\n"
                "\n"
                "# Batch arguments (-n 10 = 10 args per command):\n"
                "ls *.txt | xargs -n 10 wc -l\n"
                "\n"
                "# Replace token with -I:\n"
                "seq 1 10 | xargs -P 5 -I {} echo 'job {}'\n"
                "\n"
                "# Dry run (echo the commands):\n"
                "seq 1 3 | xargs -I {} echo curl -s https://api.example.com/{}"
    },
    default_lang='bash',
))
d18.append(new_task(
    'sed_replace',
    [r'\bsed\b.*\b(?:replace|substitute|in[- ]place|-i)\b'],
    "Here's how to replace text in a file with sed.",
    "sed 's/old/new/' replaces the first match per line; add g for all, i for case-insensitive, and -i to edit in place (use -i.bak to keep a backup).",
    {
        'bash': "# Replace first occurrence per line (print to stdout):\n"
                "sed 's/foo/bar/' file.txt\n"
                "\n"
                "# Replace ALL occurrences:\n"
                "sed 's/foo/bar/g' file.txt\n"
                "\n"
                "# In place, with a backup:\n"
                "sed -i.bak 's/foo/bar/g' file.txt\n"
                "\n"
                "# In place, no backup (GNU sed):\n"
                "sed -i 's/foo/bar/g' file.txt\n"
                "\n"
                "# Case-insensitive:\n"
                "sed -i 's/foo/bar/gi' file.txt\n"
                "\n"
                "# Line-anchored:\n"
                "sed -i '/^#/d' file.txt            # delete comment lines\n"
                "sed -i '10,20s/foo/bar/g' file.txt # lines 10-20 only\n"
                "\n"
                "# Escaping special chars:\n"
                "sed -i 's|https://old|https://new|' file.txt   # | as delimiter\n"
                "\n"
                "# macOS: sed -i '' 's/foo/bar/g' file.txt"
    },
    default_lang='bash',
))
d18.append(new_task(
    'sort_by_column',
    [r'\bsort\b.*\bcolumn\b',
     r'\bsort\s+-k\b',
     r'\bsort\b.*\bby\s+(?:a\s+)?column\b'],
    "Here's how to sort a file by a column with sort.",
    "sort -k N sorts by the Nth field. Add -n for numeric, -r for reverse, -t to set the delimiter, and -u to dedupe. -h understands human sizes (1K, 2M).",
    {
        'bash': "# Sort by the 2nd column (whitespace):\n"
                "sort -k2 data.txt\n"
                "\n"
                "# Numeric, descending:\n"
                "sort -k2 -n -r data.txt\n"
                "\n"
                "# CSV with a custom delimiter:\n"
                "sort -t, -k2 -n data.csv\n"
                "\n"
                "# Multiple keys (column 1, then 2):\n"
                "sort -k1,1 -k2,2n data.txt\n"
                "\n"
                "# Human-readable sizes (1K, 2M):\n"
                "du -sh * | sort -k1 -h -r\n"
                "\n"
                "# Deduplicate adjacent identical lines:\n"
                "sort -u data.txt\n"
                "\n"
                "# Sort with case-insensitive and unique:\n"
                "sort -f -u data.txt"
    },
    default_lang='bash',
))
d18.append(new_task(
    'duplicate_lines',
    [r'\bduplicate\s+lines\b',
     r'\b(?:find|print)\b.*\b(?:duplicate|repeated)\s+lines\b.*\bfile\b'],
    "Here's how to find duplicate lines in a file.",
    "sort + uniq -d shows lines that repeat; uniq -c counts occurrences. awk keeps the first-seen order without sorting.",
    {
        'bash': "# Duplicate lines (requires sorted input):\n"
                "sort file.txt | uniq -d\n"
                "\n"
                "# Count occurrences:\n"
                "sort file.txt | uniq -c | sort -rn\n"
                "\n"
                "# Unique lines only:\n"
                "sort file.txt | uniq\n"
                "\n"
                "# Preserve first-seen order (awk):\n"
                "awk 'seen[$0]++ {print}' file.txt          # dupes in order\n"
                "awk '!seen[$0]++' file.txt                 # uniques in order\n"
                "\n"
                "# Case-insensitive duplicates:\n"
                "sort -f file.txt | uniq -di"
    },
    default_lang='bash',
))
save('18_devops.json', d18)

# ── 13: sqlite/redis/toml/xml ──────────────────────────────────────────────
d13b = load('13_python_utils.json')
d13b.append(new_task(
    'toml_read',
    [r'\btoml\b'],
    "Here's how to read a TOML file in {lang}.",
    "Python 3.11+ has tomllib in the stdlib (read-only). For writing TOML use tomli-w. TOML is the config format for pyproject.toml and Cargo.toml.",
    {
        'python': "# Python 3.11+:\n"
                  "import tomllib\n"
                  "\n"
                  "with open('config.toml', 'rb') as f:\n"
                  "    config = tomllib.load(f)\n"
                  "\n"
                  "print(config.get('server'))\n"
                  "\n"
                  "# From a string:\n"
                  "data = tomllib.loads('port = 8000\\nhost = \"localhost\"')\n"
                  "\n"
                  "# config.toml example:\n"
                  "# [server]\n"
                  "# host = \"localhost\"\n"
                  "# port = 8000\n"
                  "#\n"
                  "# [database]\n"
                  "# url = \"postgresql://localhost/db\"",
    },
))
d13b.append(new_task(
    'xml_parse',
    [r'\b(?:parse|read|create)\b.*\bxml\b',
     r'\bxml\b.*\b(?:parse|read|elementtree)\b'],
    "Here's how to parse XML in {lang}.",
    "xml.etree.ElementTree is the stdlib choice. findall/find/iter navigate the tree; .text and .attrib access content. For huge files use iterparse to stream.",
    {
        'python': "import xml.etree.ElementTree as ET\n"
                  "\n"
                  "xml_text = '''\n"
                  "<catalog>\n"
                  "  <book id=\"1\"><title>Python 101</title><price>29.99</price></book>\n"
                  "  <book id=\"2\"><title>Rust</title><price>39.99</price></book>\n"
                  "</catalog>\n"
                  "'''\n"
                  "\n"
                  "root = ET.fromstring(xml_text)\n"
                  "\n"
                  "# From a file:\n"
                  "tree = ET.parse('data.xml')\n"
                  "root = tree.getroot()\n"
                  "\n"
                  "# Navigate:\n"
                  "for book in root.findall('book'):\n"
                  "    print(book.get('id'), book.findtext('title'), book.findtext('price'))\n"
                  "\n"
                  "# Iterate all elements:\n"
                  "for el in root.iter():\n"
                  "    print(el.tag, el.text)\n"
                  "\n"
                  "# Build XML:\n"
                  "root = ET.Element('catalog')\n"
                  "book = ET.SubElement(root, 'book', {'id': '3'})\n"
                  "ET.SubElement(book, 'title').text = 'Go'\n"
                  "print(ET.tostring(root, encoding='unicode'))",
    },
))
d13b.append(new_task(
    'sqlite_use',
    [r'\bsqlite\b'],
    "Here's how to use SQLite from {lang}.",
    "sqlite3 is in the Python stdlib. Use the connection as a context manager (auto-commit), parameterized queries for safety, and check sqlite_version for SQLite's feature level.",
    {
        'python': "import sqlite3\n"
                  "\n"
                  "conn = sqlite3.connect('app.db')   # ':memory:' for a temp db\n"
                  "\n"
                  "conn.execute('''\n"
                  "    CREATE TABLE IF NOT EXISTS users (\n"
                  "        id INTEGER PRIMARY KEY,\n"
                  "        name TEXT NOT NULL\n"
                  "    )\n"
                  "''')\n"
                  "\n"
                  "# Insert (parameterized):\n"
                  "conn.execute('INSERT INTO users (name) VALUES (?)', ('alice',))\n"
                  "conn.commit()\n"
                  "\n"
                  "# Query:\n"
                  "for row in conn.execute('SELECT * FROM users'):\n"
                  "    print(row)\n"
                  "\n"
                  "# With the connection as a context manager (auto-commit):\n"
                  "with sqlite3.connect('app.db') as conn:\n"
                  "    conn.execute('INSERT INTO users (name) VALUES (?)', ('bob',))\n"
                  "\n"
                  "# Dict rows:\n"
                  "conn.row_factory = sqlite3.Row\n"
                  "row = conn.execute('SELECT * FROM users WHERE id = ?', (1,)).fetchone()\n"
                  "print(row['name'])\n"
                  "\n"
                  "conn.close()",
    },
))
d13b.append(new_task(
    'redis_use',
    [r'\bredis\b'],
    "Here's how to use Redis from {lang}.",
    "redis-py is the standard client. Redis is an in-memory key-value store — great for caching, rate limiting, and queues. Set TTLs on caches with ex=.",
    {
        'python': "# pip install redis\n"
                  "import redis\n"
                  "\n"
                  "r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)\n"
                  "\n"
                  "# Strings:\n"
                  "r.set('user:42:name', 'alice')\n"
                  "print(r.get('user:42:name'))\n"
                  "\n"
                  "# Cache with TTL:\n"
                  "r.setex('cache:page:1', 300, 'cached-content')   # 300s\n"
                  "\n"
                  "# Increment (rate limiting):\n"
                  "r.incr('hits')\n"
                  "\n"
                  "# Lists (queues):\n"
                  "r.lpush('jobs', 'task-1')\n"
                  "job = r.rpop('jobs')\n"
                  "\n"
                  "# Hashes:\n"
                  "r.hset('user:42', mapping={'name': 'alice', 'age': 30})\n"
                  "print(r.hgetall('user:42'))\n"
                  "\n"
                  "# Sets:\n"
                  "r.sadd('online', 'alice')\n"
                  "print(r.smembers('online'))\n"
                  "\n"
                  "# Expiry check:\n"
                  "print(r.ttl('cache:page:1'))",
    },
))
save('13_python_utils.json', d13b)

print('done')
