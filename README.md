## 방향성 : TABLE의 정보를 읽고, NEO4J에 저장한다, 사용자의 질문에 대해 그래프 검색과, CODE LLM을 이용하여 최적의 SQL을 생성한다.
## 실행 조건 : 가상 환경인 .VENV에 모든 패키지는 설치되어 있어
### 구조 분석 
#### 단계 1 각 table의 Column에 대한 COMMENT, table schema, 그리고 comment를 claude로 분석하여 테이블과 컬럼의 연관 구조 neo4j에 저장함.
### 질문에 대한 쿼리 생성은 다음의 단계를 따름
#### 단계 2 codellama을 이용하여 어떠한 테이블이 대상이 되는지 neo4j 검색을 통해 확인
#### 단계 3 codellama을 이용하여 어떠한 컬럼을 선택해야 하는지 neo4j 검색을 통해 확인
#### 단계 4 neo4j 검색 결과의 테이블, 컬럼이 실제 테이블, 컬럼과 일치하는지 확인
#### 단계 5 최종으로 codellama을 이용하여 쿼리 생성

#### 주요 기법
1. TABLE의 컬럼 속성, COMMENT등을 모두 NEO4J의 노드로 변환해야 함.
2. 질문에 적합한 테이블과 컬럼을 얻기 위해 NEO4J을 우선 탐색함.
3. 탐색 결과를 이용, SQL로 변환.

#### 테스트 질문 : 사용자 정보를 조회해줘

#### 결과 : 
~~~
> Entering new GraphCypherQAChain chain...
Generated Cypher:
MATCH (t:Table {name: 'users'})-[:HAS_COLUMN]->(c:Column)
RETURN c.name as column_name
Full Context:
[{'column_name': 'status'}, {'column_name': 'created_at'}, {'column_name': 'full_name'}, {'column_name': 'email'}, {'column_name': 'username'}, {'column_name': 'user_id'}]

> Finished chain.

📝 생성된 Cypher 쿼리:
```cypher
MATCH (t:Table {name: 'users'})-[:HAS_COLUMN]->(c:Column) RETURN c.name as column_name
```

📊 Neo4j 쿼리 결과:
     column_name
     column_name
   ---------------
       status
     created_at
     column_name
   ---------------
     column_name
   ---------------
       status
     created_at
      full_name
        email
      username
       user_id

🔄 변환된 SQL 쿼리:
```sql
SELECT created_at, email, full_name, status, user_id, username
FROM users;
```

⚡ SQL 쿼리 실행 중...
✅ SQL 쿼리 실행 성공!

📊 SQL 실행 결과:
     created_at    |      email      |    full_name    |     status      |     user_id     |    username
   ---------------------------------------------------------------------------------------------------------
   2025-07-27 07:22:41 | john@example... |       홍길동       |     active      |        1        |    john_doe
   2025-07-27 07:22:41 | jane@example... |       김영희       |     active      |        2        |   jane_smith
   2025-07-27 07:22:41 | bob@example.com |       박철수       |     active      |        3        |   bob_wilson
   2025-07-27 07:22:41 | alice@exampl... |       이순신       |    inactive     |        4        |   alice_brown
   2025-07-27 07:22:41 | charlie@exam... |       정약용       |     active      |        5        |  charlie_davis

~~~