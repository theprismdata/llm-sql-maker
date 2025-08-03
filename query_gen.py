"""
LangChain Neo4j를 이용한 SQL 쿼리 생성 (OLLAMA + CodeLlama)
"""

import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# LangChain 및 Neo4j 관련 import
from langchain.chains import GraphQAChain
from langchain_neo4j import Neo4jGraph
from langchain_neo4j import GraphCypherQAChain
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.schema import Document

import pymysql

class Neo4jQueryGenerator:
    def __init__(self):
        """Neo4j 쿼리 생성기 초기화"""
        
        # Neo4j 연결 정보
        self.neo4j_config = {
            'url': 'bolt://localhost:7687',
            'username': 'neo4j',
            'password': 'password123'
        }
        
        # MariaDB 연결 정보
        self.mariadb_config = {
            'host': 'localhost',
            'port': 32000,
            'user': 'genai',
            'password': 'genai1234',
            'database': 'llm_db_test',
            'charset': 'utf8mb4'
        }
        
        # OLLAMA 설정
        self.ollama_url = "http://localhost:11434"
        # self.ollama_graph_query_model = "codellama:7b"
        self.ollama_graph_query_model = "gemma3:12b"
        
        # LangChain 구성 요소
        self.graph = None
        self.llm = None
        self.chain = None
        self.mariadb_conn = None
        
        self._initialize_components()
    
    def _initialize_components(self):
        """LangChain 구성 요소 초기화"""
        try:
            # Neo4j 그래프 연결
            print("🔄 Neo4j 그래프 연결 중...")
            self.graph = Neo4jGraph(
                url=self.neo4j_config['url'],
                username=self.neo4j_config['username'],
                password=self.neo4j_config['password']
            )
            print("✅ Neo4j 그래프 연결 성공!")
            
            # MariaDB 연결
            print("🔄 MariaDB 연결 중...")
            self.mariadb_conn = pymysql.connect(**self.mariadb_config)
            print("✅ MariaDB 연결 성공!")
            
            # 스키마 초기화
            self._init_schema()
            
            # OLLAMA LLM 초기화
            print("🔄 OLLAMA LLM 초기화 중...")
            self.llm = OllamaLLM(
                base_url=self.ollama_url,
                model=self.ollama_graph_query_model,
                temperature=0.1
            )
            print(f"✅ OLLAMA LLM 초기화 성공! (모델: {self.ollama_graph_query_model})")
            
            # GraphCypherQAChain 생성
            self.get_GraphCypherQAChain()
            
        except Exception as e:
            print(f"❌ 초기화 실패: {e}")
            raise
    
    def _init_schema(self):
        """RDB 스키마 정보를 Neo4j에 저장"""
        try:
            print("🔄 RDB 스키마 정보를 Neo4j에 저장 중...")
            
            # 기존 데이터 삭제
            self.graph.query("MATCH (n) DETACH DELETE n")
            
            # 테이블 노드 생성
            tables = [
                {
                    "name": "users",
                    "comment": "사용자 계정 정보를 저장하는 테이블",
                    "columns": [
                        {"name": "user_id", "type": "INT", "is_pk": True, "comment": "사용자 고유 식별자"},
                        {"name": "username", "type": "VARCHAR(50)", "comment": "사용자명 (로그인 ID)"},
                        {"name": "email", "type": "VARCHAR(100)", "comment": "이메일 주소"},
                        {"name": "full_name", "type": "VARCHAR(100)", "comment": "사용자 실명"},
                        {"name": "created_at", "type": "TIMESTAMP", "comment": "계정 생성일시"},
                        {"name": "status", "type": "ENUM", "values": ["active", "inactive", "suspended"], "comment": "계정 상태"}
                    ]
                },
                {
                    "name": "products",
                    "comment": "판매 상품 정보를 저장하는 테이블",
                    "columns": [
                        {"name": "product_id", "type": "INT", "is_pk": True, "comment": "상품 고유 식별자"},
                        {"name": "product_name", "type": "VARCHAR(200)", "comment": "상품명"},
                        {"name": "category_id", "type": "INT", "comment": "소속 카테고리 ID"},
                        {"name": "price", "type": "DECIMAL(10,2)", "comment": "상품 가격"},
                        {"name": "stock_quantity", "type": "INT", "comment": "재고 수량"},
                        {"name": "description", "type": "TEXT", "comment": "상품 상세 설명"},
                        {"name": "status", "type": "ENUM", "values": ["active", "inactive", "discontinued"], "comment": "상품 판매 상태"}
                    ]
                },
                {
                    "name": "orders",
                    "comment": "사용자 주문 정보를 저장하는 테이블",
                    "columns": [
                        {"name": "order_id", "type": "INT", "is_pk": True, "comment": "주문 고유 식별자"},
                        {"name": "user_id", "type": "INT", "comment": "주문한 사용자 ID"},
                        {"name": "order_date", "type": "TIMESTAMP", "comment": "주문 생성일시"},
                        {"name": "total_amount", "type": "DECIMAL(10,2)", "comment": "주문 총 금액"},
                        {"name": "status", "type": "ENUM", "values": ["pending", "processing", "shipped", "delivered", "cancelled"], "comment": "주문 처리 상태"},
                        {"name": "shipping_address", "type": "TEXT", "comment": "배송 주소"}
                    ]
                },
                {
                    "name": "order_items",
                    "comment": "주문에 포함된 개별 상품 정보를 저장하는 테이블",
                    "columns": [
                        {"name": "order_item_id", "type": "INT", "is_pk": True, "comment": "주문 상세 고유 식별자"},
                        {"name": "order_id", "type": "INT", "comment": "주문 ID"},
                        {"name": "product_id", "type": "INT", "comment": "주문된 상품 ID"},
                        {"name": "quantity", "type": "INT", "comment": "주문 수량"},
                        {"name": "unit_price", "type": "DECIMAL(10,2)", "comment": "주문 당시 상품 단가"},
                        {"name": "subtotal", "type": "DECIMAL(10,2)", "comment": "해당 상품의 주문 소계"}
                    ]
                },
                {
                    "name": "categories",
                    "comment": "상품 카테고리 정보를 저장하는 테이블",
                    "columns": [
                        {"name": "category_id", "type": "INT", "is_pk": True, "comment": "카테고리 고유 식별자"},
                        {"name": "category_name", "type": "VARCHAR(100)", "comment": "카테고리명"},
                        {"name": "parent_category_id", "type": "INT", "comment": "상위 카테고리 ID"},
                        {"name": "description", "type": "TEXT", "comment": "카테고리 설명"}
                    ]
                }
            ]
            
            # 테이블과 컬럼 노드 생성
            for table in tables:
                # 테이블 노드 생성
                self.graph.query(f"""
                CREATE (t:Table {{
                    name: '{table["name"]}',
                    comment: '{table["comment"]}'
                }})
                """)
                
                # 컬럼 노드 생성 및 연결
                for col in table["columns"]:
                    col_props = {
                        "name": col["name"],
                        "type": col["type"],
                        "comment": col["comment"],
                        "is_pk": col.get("is_pk", False)
                    }
                    if "values" in col:
                        col_props["enum_values"] = ",".join(col["values"])
                    
                    # 속성 문자열 생성
                    props_str = ", ".join(f"{k}: '{v}'" for k, v in col_props.items())
                    
                    self.graph.query(f"""
                    MATCH (t:Table {{name: '{table["name"]}'}})
                    CREATE (c:Column {{{props_str}}})
                    CREATE (t)-[:HAS_COLUMN]->(c)
                    """)
            
            # 외래키 관계 생성
            foreign_keys = [
                ("orders", "user_id", "users", "user_id"),
                ("order_items", "order_id", "orders", "order_id"),
                ("order_items", "product_id", "products", "product_id"),
                ("products", "category_id", "categories", "category_id"),
                ("categories", "parent_category_id", "categories", "category_id")
            ]
            
            for from_table, from_col, to_table, to_col in foreign_keys:
                self.graph.query(f"""
                MATCH (t1:Table {{name: '{from_table}'}})-[:HAS_COLUMN]->(c1:Column {{name: '{from_col}'}})
                MATCH (t2:Table {{name: '{to_table}'}})-[:HAS_COLUMN]->(c2:Column {{name: '{to_col}'}})
                CREATE (c1)-[:REFERENCES]->(c2)
                """)
            
            print("✅ RDB 스키마 정보 저장 완료!")
            
        except Exception as e:
            print(f"❌ 스키마 초기화 실패: {e}")
            raise
    
#     def _get_cypher_prompt(self) -> PromptTemplate:
#         """Cypher 쿼리 생성을 위한 프롬프트 템플릿"""
#         template = """You are a Neo4j expert. Given the schema and question, generate a Cypher query to answer the question.

# Schema of the Neo4j database:
# Tables are represented as (:Table) nodes with properties:
# - name: table name (e.g., 'users', 'orders')
# - description: table description

# Columns are represented as (:Column) nodes with properties:
# - name: column name (e.g., 'id', 'username', 'email')

# Relationships:
# - (:Table)-[:HAS_COLUMN]->(:Column): table has this column
# - (:Column)-[:REFERENCES]->(:Column): foreign key relationship

# Example valid queries:
# 1. Find all columns of users table:
#    MATCH (t:Table {name: 'users'})-[:HAS_COLUMN]->(c:Column)
#    RETURN t.name as table, c.name as column

# 2. Find related tables through foreign keys:
#    MATCH (t1:Table)-[:HAS_COLUMN]->(c1:Column)-[:REFERENCES]->(c2:Column)<-[:HAS_COLUMN]-(t2:Table)
#    RETURN t1.name as from_table, c1.name as from_column, t2.name as to_table, c2.name as to_column

# Question: {query}

# Generate a Cypher query that answers this question.
# Use only the node labels, properties, and relationship types mentioned above.
# The query should return meaningful data that answers the question.
# Return column names with aliases for clarity.

# Cypher Query:"""
        
#         return PromptTemplate(
#             template=template,
#             input_variables=["query"]
#         )
    
    def _execute_sql(self, sql_query: str) -> Optional[List[Dict]]:
        """SQL 쿼리 실행"""
        try:
            print("\n⚡ SQL 쿼리 실행 중...")
            with self.mariadb_conn.cursor() as cursor:
                cursor.execute(sql_query)
                
                # SELECT 쿼리인 경우 결과 반환
                if sql_query.strip().upper().startswith('SELECT'):
                    results = cursor.fetchall()
                    # 컬럼 이름 가져오기
                    columns = [desc[0] for desc in cursor.description]
                    
                    # 결과를 딕셔너리 리스트로 변환
                    result_dicts = []
                    for row in results:
                        result_dicts.append(dict(zip(columns, row)))
                    
                    print("✅ SQL 쿼리 실행 성공!")
                    return result_dicts
                else:
                    # INSERT, UPDATE 등의 경우 커밋
                    self.mariadb_conn.commit()
                    print("✅ SQL 쿼리 실행 성공!")
                    return None
                
        except Exception as e:
            print(f"❌ SQL 쿼리 실행 실패: {e}")
            return None
    
    def get_GraphCypherQAChain(self):
        """GraphCypherQAChain 생성"""
        try:
            print("🔄 GraphCypherQAChain 생성 중...")
            
            # 커스텀 프롬프트 생성
            cypher_prompt = PromptTemplate(
                template="""You are a Neo4j expert. Return ONLY a Cypher query without any explanation.

IMPORTANT - READ CAREFULLY:
1. Return ONLY the Cypher query, no explanations or comments
2. The query MUST start with MATCH
3. When looking for table columns, ALWAYS return c.name as column_name
4. Do NOT filter for specific columns - return ALL columns of the table
5. This Neo4j database contains metadata about an RDB schema:
   - (:Table) nodes represent database tables
   - (:Column) nodes represent table columns
   - [:HAS_COLUMN] shows which columns belong to which tables
   - [:REFERENCES] shows foreign key relationships

Example valid responses:
1. Get all columns of users table:
   MATCH (t:Table {{name: 'users'}})-[:HAS_COLUMN]->(c:Column)
   RETURN c.name as column_name

2. Get all columns of orders table:
   MATCH (t:Table {{name: 'orders'}})-[:HAS_COLUMN]->(c:Column)
   RETURN c.name as column_name

Schema: {schema}

Question: {query}

Return ONLY the Cypher query that gets ALL columns of the relevant table:""",
                input_variables=["schema", "query"]
            )
            
            # 체인 생성
            self.chain = GraphCypherQAChain.from_llm(
                llm=self.llm,
                graph=self.graph,
                verbose=True,
                return_intermediate_steps=True,
                allow_dangerous_requests=True,  # 보안 경고 허용
                cypher_prompt=cypher_prompt
            )
            
            print("✅ GraphCypherQAChain 생성 완료!")
            
        except Exception as e:
            print(f"❌ 체인 생성 실패: {e}")
            raise
    
    def _clean_cypher_query(self, response: str) -> str:
        """LLM 응답에서 순수한 Cypher 쿼리만 추출"""
        import re
        
        # 설명이나 주석 제거
        lines = response.strip().split('\n')
        query_lines = []
        for line in lines:
            line = line.strip()
            # 주석이나 설명 라인 무시
            if line.startswith(('/*', '--', '//', '#', 'This', 'Note', 'Here')):
                continue
            # 빈 라인 무시
            if not line:
                continue
            # 마크다운 코드 블록 표시 제거
            if line.startswith('```') or line.endswith('```'):
                continue
            query_lines.append(line)
        
        # 쿼리 합치기
        query = ' '.join(query_lines)
        
        # MATCH로 시작하는지 확인
        if not query.upper().startswith('MATCH'):
            # MATCH 키워드 찾기
            match = re.search(r'MATCH\s+.*$', query, re.IGNORECASE | re.DOTALL)
            if match:
                query = match.group(0)
            else:
                raise ValueError("No valid Cypher query found (must start with MATCH)")
        
        return query
    
    def generate_query(self, user_request: str) -> Optional[str]:
        """사용자 요청에 따른 쿼리 생성"""
        try:
            print(f"\n🤖 사용자 요청 분석 중: {user_request}")
            
            # GraphCypherQAChain 실행 (invoke 메서드 사용)
            result = self.chain.invoke({"query": user_request})
            
            # 결과 출력
            if 'intermediate_steps' in result:
                cypher_query = result['intermediate_steps'][0]['query']
                
                # Cypher 쿼리 정리
                try:
                    cypher_query = self._clean_cypher_query(cypher_query)
                except ValueError as e:
                    print(f"⚠️ 잘못된 Cypher 쿼리: {e}")
                    return None
                
                print(f"\n📝 생성된 Cypher 쿼리:")
                print(f"```cypher\n{cypher_query}\n```")
                
                # Cypher 쿼리 실행 및 결과 처리
                query_result = self.graph.query(cypher_query)
                if query_result:
                    print("\n📊 Neo4j 쿼리 결과:")
                    self._display_results(query_result)
                
                # SQL 쿼리로 변환
                sql_query = self._convert_to_sql(cypher_query, query_result)
                if sql_query:
                    print(f"\n🔄 변환된 SQL 쿼리:")
                    print(f"```sql\n{sql_query}\n```")
                    
                    # SQL 쿼리 자동 실행
                    sql_results = self._execute_sql(sql_query)
                    if sql_results:
                        print("\n📊 SQL 실행 결과:")
                        self._display_results(sql_results)
                    
                    return sql_query
            
            return None
            
        except Exception as e:
            print(f"❌ 쿼리 생성 실패: {e}")
            return None
    
    def _convert_to_sql(self, cypher_query: str, cypher_results: List[Dict]) -> Optional[str]:
        """Cypher 쿼리를 SQL로 변환"""
        try:
            # Cypher 결과에서 컬럼 정보 추출
            if not cypher_results:
                return None
            
            # 결과에서 컬럼 이름들을 추출
            columns = []
            for result in cypher_results:
                # column_name이 있는 경우 (기본 컬럼 조회)
                if 'column_name' in result:
                    columns.append(result['column_name'])
                # name이 있는 경우 (대체 형식)
                elif 'name' in result:
                    columns.append(result['name'])
            
            # 중복 제거 및 정렬
            columns = sorted(set(columns))
            
            if not columns:
                print("⚠️ 컬럼 정보를 찾을 수 없습니다.")
                return None
            
            # 테이블 이름 추출 (Cypher 쿼리에서)
            import re
            # 더 유연한 정규식 패턴으로 수정
            table_match = re.search(r"Table\s*{.*?name:\s*'(\w+)'.*?}", cypher_query, re.IGNORECASE)
            if not table_match:
                # 대체 패턴 시도
                table_match = re.search(r"Table.*?name:\s*'(\w+)'", cypher_query, re.IGNORECASE)
            
            if not table_match:
                print("⚠️ 테이블 정보를 찾을 수 없습니다.")
                return None
            
            table_name = table_match.group(1)
            
            # SQL SELECT 쿼리 생성
            sql_query = f"SELECT {', '.join(columns)}\nFROM {table_name};"
            
            return sql_query
            
        except Exception as e:
            print(f"❌ SQL 변환 실패: {e}")
            return None
    
    def _display_results(self, results: List[Dict]):
        """쿼리 결과를 보기 좋게 표시"""
        if not results:
            return
        
        # 컬럼 헤더 추출
        headers = list(results[0].keys())
        
        # 헤더 출력
        header_line = " | ".join(f"{h:^15}" for h in headers)
        print("   " + header_line)
        print("   " + "-" * len(header_line))
        
        # 데이터 출력 (최대 10개 행)
        for row in results[:10]:
            values = []
            for header in headers:
                value = row.get(header, None)
                if value is None:
                    values.append("NULL")
                elif isinstance(value, str) and len(value) > 15:
                    values.append(value[:12] + "...")
                else:
                    values.append(str(value))
            print("   " + " | ".join(f"{v:^15}" for v in values))
        
        # 더 많은 결과가 있다면 표시
        if len(results) > 10:
            print(f"\n   ... 그리고 {len(results) - 10}개의 결과가 더 있습니다.")
    
    def run_interactive_mode(self):
        """대화형 모드 실행"""
        print("=" * 70)
        print("🚀 LangChain Neo4j SQL 쿼리 생성기")
        print(f"💡 OLLAMA 모델: {self.ollama_graph_query_model}")
        print("=" * 70)
        
        print("\n💡 대화형 모드")
        print("종료하려면 'quit' 또는 'exit'를 입력하세요")
        print("=" * 50)
        
        while True:
            try:
                user_input = input("\n📝 검색하고 싶은 내용을 설명해주세요: ").strip()
                
                if user_input.lower() in ['quit', 'exit', '종료']:
                    break
                
                if not user_input:
                    continue
                
                # 쿼리 생성 및 실행
                result = self.generate_query(user_input)
                if not result:
                    print("❌ 쿼리 생성에 실패했습니다.")
                
            except KeyboardInterrupt:
                print("\n\n👋 프로그램을 종료합니다.")
                break
            except Exception as e:
                print(f"❌ 오류 발생: {e}")
                continue
        
        # 연결 종료
        if self.mariadb_conn:
            self.mariadb_conn.close()
            print("🔌 MariaDB 연결 종료")
        
        print("👋 LangChain Neo4j 쿼리 생성기를 종료합니다.")

def main():
    """메인 함수"""
    try:
        generator = Neo4jQueryGenerator()
        generator.run_interactive_mode()
    except Exception as e:
        print(f"❌ 프로그램 시작 실패: {e}")

if __name__ == "__main__":
    main()