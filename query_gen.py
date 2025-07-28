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

class Neo4jQueryGenerator:
    def __init__(self):
        """Neo4j 쿼리 생성기 초기화"""
        
        # Neo4j 연결 정보
        self.neo4j_config = {
            'url': 'bolt://localhost:7687',
            'username': 'neo4j',
            'password': 'password123'
        }
        
        # OLLAMA 설정
        self.ollama_url = "http://localhost:11434"
        self.ollama_model = "codellama:7b"
        
        # LangChain 구성 요소
        self.graph = None
        self.llm = None
        self.chain = None
        
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
            
            # 스키마 초기화
            self._init_schema()
            
            # OLLAMA LLM 초기화
            print("🔄 OLLAMA LLM 초기화 중...")
            self.llm = OllamaLLM(
                base_url=self.ollama_url,
                model=self.ollama_model,
                temperature=0.1
            )
            print(f"✅ OLLAMA LLM 초기화 성공! (모델: {self.ollama_model})")
            
            # GraphCypherQAChain 생성
            self._create_chain()
            
        except Exception as e:
            print(f"❌ 초기화 실패: {e}")
            raise
    
    def _init_schema(self):
        """Neo4j 스키마 초기화"""
        try:
            print("🔄 스키마 초기화 중...")
            
            # 기존 데이터 삭제
            self.graph.query("MATCH (n) DETACH DELETE n")
            
            # 테이블 노드 생성
            tables = [
                ("users", "사용자 정보 테이블", ["id", "username", "email", "created_at"]),
                ("orders", "주문 정보 테이블", ["id", "user_id", "total", "status"]),
                ("products", "상품 정보 테이블", ["id", "name", "price", "stock"]),
                ("categories", "카테고리 테이블", ["id", "name", "parent_id"])
            ]
            
            for table_name, desc, columns in tables:
                # 테이블 노드 생성
                self.graph.query(f"""
                CREATE (t:Table {{
                    name: '{table_name}',
                    description: '{desc}'
                }})
                """)
                
                # 컬럼 노드 생성 및 연결
                for col in columns:
                    self.graph.query(f"""
                    MATCH (t:Table {{name: '{table_name}'}})
                    CREATE (c:Column {{name: '{col}'}})
                    CREATE (t)-[:HAS_COLUMN]->(c)
                    """)
            
            # 테이블 간 관계 생성
            relations = [
                ("orders", "user_id", "users", "id"),
                ("products", "category_id", "categories", "id")
            ]
            
            for from_table, from_col, to_table, to_col in relations:
                self.graph.query(f"""
                MATCH (t1:Table {{name: '{from_table}'}})-[:HAS_COLUMN]->(c1:Column {{name: '{from_col}'}})
                MATCH (t2:Table {{name: '{to_table}'}})-[:HAS_COLUMN]->(c2:Column {{name: '{to_col}'}})
                CREATE (c1)-[:REFERENCES]->(c2)
                """)
            
            print("✅ 스키마 초기화 완료!")
            
        except Exception as e:
            print(f"❌ 스키마 초기화 실패: {e}")
            raise
    
    def _get_cypher_prompt(self) -> PromptTemplate:
        """Cypher 쿼리 생성을 위한 프롬프트 템플릿"""
        template = """You are a Neo4j expert. Given the schema and question, generate a Cypher query to answer the question.

Schema of the Neo4j database:
Tables are represented as (:Table) nodes with properties:
- name: table name (e.g., 'users', 'orders')
- description: table description

Columns are represented as (:Column) nodes with properties:
- name: column name (e.g., 'id', 'username', 'email')

Relationships:
- (:Table)-[:HAS_COLUMN]->(:Column): table has this column
- (:Column)-[:REFERENCES]->(:Column): foreign key relationship

Example valid queries:
1. Find all columns of users table:
   MATCH (t:Table {name: 'users'})-[:HAS_COLUMN]->(c:Column)
   RETURN t.name as table, c.name as column

2. Find related tables through foreign keys:
   MATCH (t1:Table)-[:HAS_COLUMN]->(c1:Column)-[:REFERENCES]->(c2:Column)<-[:HAS_COLUMN]-(t2:Table)
   RETURN t1.name as from_table, c1.name as from_column, t2.name as to_table, c2.name as to_column

Question: {query}

Generate a Cypher query that answers this question.
Use only the node labels, properties, and relationship types mentioned above.
The query should return meaningful data that answers the question.
Return column names with aliases for clarity.

Cypher Query:"""
        
        return PromptTemplate(
            template=template,
            input_variables=["query"]
        )
    
    def generate_query(self, user_request: str) -> Optional[str]:
        """사용자 요청에 따른 쿼리 생성"""
        try:
            print(f"\n🤖 사용자 요청 분석 중: {user_request}")
            
            # GraphCypherQAChain 실행 (invoke 메서드 사용)
            result = self.chain.invoke({"query": user_request})
            
            # 결과 출력
            if 'intermediate_steps' in result:
                cypher_query = result['intermediate_steps'][0]['query']
                print(f"\n📝 생성된 Cypher 쿼리:")
                print(f"```cypher\n{cypher_query}\n```")
                
                # 쿼리 실행 및 결과 처리
                query_result = self.graph.query(cypher_query)
                if query_result:
                    print("\n📊 쿼리 결과:")
                    self._display_results(query_result)
                else:
                    print("\n⚠️ 결과가 없습니다.")
            
            return result.get('result', '')
            
        except Exception as e:
            print(f"❌ 쿼리 생성 실패: {e}")
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
    
    def _create_chain(self):
        """GraphCypherQAChain 생성"""
        try:
            print("🔄 GraphCypherQAChain 생성 중...")
            
            # 체인 생성
            self.chain = GraphCypherQAChain.from_llm(
                llm=self.llm,
                graph=self.graph,
                verbose=True,
                return_intermediate_steps=True,
                allow_dangerous_requests=True  # 보안 경고 허용
            )
            
            print("✅ GraphCypherQAChain 생성 완료!")
            
        except Exception as e:
            print(f"❌ 체인 생성 실패: {e}")
            raise
    
    def run_interactive_mode(self):
        """대화형 모드 실행"""
        print("=" * 70)
        print("🚀 LangChain Neo4j 쿼리 생성기")
        print(f"💡 OLLAMA 모델: {self.ollama_model}")
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
                
                # 쿼리 생성
                result = self.generate_query(user_input)
                if not result:
                    print("❌ 쿼리 생성에 실패했습니다.")
                
            except KeyboardInterrupt:
                print("\n\n👋 프로그램을 종료합니다.")
                break
            except Exception as e:
                print(f"❌ 오류 발생: {e}")
                continue
        
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