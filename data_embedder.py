"""
데이터 임베딩 모듈
MariaDB 데이터를 Neo4j에 하이브리드 방식으로 임베딩
- 스키마 메타데이터
- 실제 데이터 그래프화
- 텍스트 벡터 임베딩
"""

import os
import pymysql
from typing import List, Dict, Any, Optional
from langchain_neo4j import Neo4jGraph
from langchain_huggingface import HuggingFaceEmbeddings

class DataEmbedder:
    def __init__(self, neo4j_config: Dict, mariadb_config: Dict, model_name: str = "BAAI/bge-m3"):
        """데이터 임베딩 클래스 초기화"""
        
        self.neo4j_config = neo4j_config
        self.mariadb_config = mariadb_config
        self.model_name = model_name
        
        # 연결 객체
        self.graph = None
        self.mariadb_conn = None
        self.embeddings = None
        
        self._initialize_connections()
    
    def _initialize_connections(self):
        """필요한 연결들 초기화"""
        try:
            # Neo4j 연결
            print("🔄 Neo4j 연결 초기화 중...")
            self.graph = Neo4jGraph(
                url=self.neo4j_config['url'],
                username=self.neo4j_config['username'],
                password=self.neo4j_config['password']
            )
            print("✅ Neo4j 연결 성공!")
            
            # MariaDB 연결
            print("🔄 MariaDB 연결 초기화 중...")
            self.mariadb_conn = pymysql.connect(**self.mariadb_config)
            print("✅ MariaDB 연결 성공!")
            
            # 임베딩 모델 초기화
            print(f"🔄 임베딩 모델 다운로드 및 초기화 중... ({self.model_name})")
            
            # 로컬 모델 캐시 경로 확인 (HuggingFace 캐시 구조)
            cache_folder = os.getcwd()
            model_cache_name = self.model_name.replace("/", "--")
            local_model_path = os.path.join(cache_folder, f"models--{model_cache_name}")
            
            if os.path.exists(local_model_path):
                print(f"✅ 로컬 모델 발견: {local_model_path}")
                print("🔄 로컬 모델로 임베딩 초기화 중...")
            else:
                print(f"❌ 로컬 모델 없음. 다운로드 시작: {self.model_name}")
                print(f"📁 다운로드 경로: {cache_folder}")
            
            self.embeddings = HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs={'device': 'cpu'},  # GPU 사용시 'cuda'로 변경
                encode_kwargs={'normalize_embeddings': True},
                cache_folder=cache_folder  # 현재 디렉토리에 모델 다운로드
            )
            print("✅ 임베딩 모델 초기화 성공!")
            
        except Exception as e:
            print(f"❌ 연결 초기화 실패: {e}")
            raise
    
    def _execute_sql(self, sql_query: str) -> Optional[List[Dict]]:
        """SQL 쿼리 실행하여 결과 반환"""
        try:
            with self.mariadb_conn.cursor() as cursor:
                cursor.execute(sql_query)
                
                # 결과를 반환하는 쿼리 타입들 (SELECT, SHOW, DESCRIBE 등)
                query_upper = sql_query.strip().upper()
                if query_upper.startswith(('SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN')):
                    results = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    
                    result_dicts = []
                    for row in results:
                        result_dicts.append(dict(zip(columns, row)))
                    
                    return result_dicts
                else:
                    # INSERT, UPDATE, DELETE 등의 쿼리
                    self.mariadb_conn.commit()
                    return None
                
        except Exception as e:
            print(f"❌ SQL 쿼리 실행 실패: {e}")
            return None
    
    def clear_neo4j_data(self):
        """Neo4j의 모든 데이터 삭제"""
        try:
            print("🔄 Neo4j 기존 데이터 삭제 중...")
            self.graph.query("MATCH (n) DETACH DELETE n")
            print("✅ Neo4j 데이터 삭제 완료!")
        except Exception as e:
            print(f"❌ 데이터 삭제 실패: {e}")
            raise
    
    def embed_schema_metadata(self):
        """스키마 메타데이터를 MariaDB에서 동적으로 읽어와 Neo4j에 임베딩"""
        try:
            print("🔄 스키마 메타데이터 임베딩 중...")
            
            # 테이블 목록 조회
            tables_info = self._execute_sql("SHOW TABLES")
            table_names = [list(table.values())[0] for table in tables_info]
            
            # 각 테이블의 컬럼 정보와 코멘트 조회
            for table_name in table_names:
                # 테이블 코멘트 조회
                table_comment_result = self._execute_sql(f"""
                    SELECT TABLE_COMMENT 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = '{self.mariadb_config['database']}' 
                    AND TABLE_NAME = '{table_name}'
                """)
                table_comment = table_comment_result[0]['TABLE_COMMENT'] if table_comment_result else ""
                
                # 테이블 노드 생성
                self.graph.query(f"""
                CREATE (t:Table {{
                    name: '{table_name}',
                    comment: '{table_comment}'
                }})
                """)
                
                # 컬럼 정보 조회
                columns_info = self._execute_sql(f"""
                    SELECT COLUMN_NAME, DATA_TYPE, COLUMN_KEY, COLUMN_COMMENT, COLUMN_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = '{self.mariadb_config['database']}' 
                    AND TABLE_NAME = '{table_name}'
                    ORDER BY ORDINAL_POSITION
                """)
                
                # 컬럼 노드 생성
                for col in columns_info:
                    is_pk = col['COLUMN_KEY'] == 'PRI'
                    
                    # enum 타입 처리
                    column_type = col['COLUMN_TYPE']
                    if column_type.startswith('enum('):
                        # enum 값들을 문자열로 변환
                        enum_values = column_type.replace('enum(', '').replace(')', '').replace("'", '').split(',')
                        enum_values = [v.strip() for v in enum_values]
                        column_type = 'enum(' + ','.join(enum_values) + ')'
                    
                    self.graph.query(f"""
                    MATCH (t:Table {{name: '{table_name}'}})
                    CREATE (c:Column {{
                        name: '{col['COLUMN_NAME']}',
                        type: '{column_type}',
                        comment: '{col['COLUMN_COMMENT']}',
                        is_pk: {str(is_pk).lower()}
                    }})
                    CREATE (t)-[:HAS_COLUMN]->(c)
                    """)
            
            # 외래키 관계 조회 및 생성
            fk_info = self._execute_sql(f"""
                SELECT 
                    TABLE_NAME,
                    COLUMN_NAME,
                    REFERENCED_TABLE_NAME,
                    REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = '{self.mariadb_config['database']}'
                AND REFERENCED_TABLE_NAME IS NOT NULL
            """)
            
            for fk in fk_info:
                self.graph.query(f"""
                MATCH (t1:Table {{name: '{fk['TABLE_NAME']}'}})-[:HAS_COLUMN]->(c1:Column {{name: '{fk['COLUMN_NAME']}'}})
                MATCH (t2:Table {{name: '{fk['REFERENCED_TABLE_NAME']}'}})-[:HAS_COLUMN]->(c2:Column {{name: '{fk['REFERENCED_COLUMN_NAME']}'}})
                CREATE (c1)-[:REFERENCES]->(c2)
                """)
            
            print("✅ 스키마 메타데이터 임베딩 완료!")
            
        except Exception as e:
            print(f"❌ 스키마 임베딩 실패: {e}")
            raise
    
    def embed_actual_data(self):
        """실제 테이블 데이터를 Neo4j 그래프로 변환"""
        try:
            print("🔄 실제 데이터 그래프화 중...")
            
            # 모든 테이블 목록 가져오기
            tables_info = self._execute_sql("SHOW TABLES")
            table_names = [list(table.values())[0] for table in tables_info]
            
            # 각 테이블의 데이터를 Node로 변환
            for table_name in table_names:
                print(f"   📄 {table_name} 테이블 처리 중...")
                
                # 테이블의 모든 데이터 조회
                table_data = self._execute_sql(f"SELECT * FROM {table_name}")
                
                # 각 행을 노드로 생성
                for row in table_data:
                    # 노드 속성 문자열 생성
                    props = []
                    for key, value in row.items():
                        if value is not None:
                            # 모든 값을 문자열로 처리 (enum 포함)
                            value_str = str(value).replace(chr(39), chr(92)+chr(39))
                            props.append(f"{key}: '{value_str}'")
                    
                    props_str = ", ".join(props)
                    node_label = table_name.capitalize()
                    
                    self.graph.query(f"""
                    CREATE (n:{node_label} {{{props_str}}})
                    """)
            
            print("✅ 실제 데이터 그래프화 완료!")
            
        except Exception as e:
            print(f"❌ 데이터 그래프화 실패: {e}")
            raise
    
    def embed_text_vectors(self):
        """텍스트 데이터를 벡터로 변환하여 임베딩"""
        try:
            print("🔄 텍스트 벡터 임베딩 중...")
            
            # 모든 테이블의 텍스트 컬럼들을 찾아서 벡터화
            tables_info = self._execute_sql("SHOW TABLES")
            table_names = [list(table.values())[0] for table in tables_info]
            
            for table_name in table_names:
                print(f"   📄 {table_name} 텍스트 임베딩 중...")
                
                # 텍스트 타입 컬럼 찾기
                text_columns_info = self._execute_sql(f"""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = '{self.mariadb_config['database']}' 
                    AND TABLE_NAME = '{table_name}'
                    AND DATA_TYPE IN ('text', 'varchar', 'longtext', 'mediumtext')
                    AND CHARACTER_MAXIMUM_LENGTH > 50
                """)
                
                if not text_columns_info:
                    continue
                
                text_columns = [col['COLUMN_NAME'] for col in text_columns_info]
                
                # ID 컬럼 찾기 (주로 첫 번째 컬럼이거나 _id로 끝나는 컬럼)
                id_column_info = self._execute_sql(f"""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = '{self.mariadb_config['database']}' 
                    AND TABLE_NAME = '{table_name}'
                    AND (COLUMN_KEY = 'PRI' OR COLUMN_NAME LIKE '%_id')
                    ORDER BY ORDINAL_POSITION LIMIT 1
                """)
                
                if not id_column_info:
                    continue
                    
                id_column = id_column_info[0]['COLUMN_NAME']
                
                # 데이터 조회 및 벡터화
                columns_to_select = [id_column] + text_columns
                table_data = self._execute_sql(f"SELECT {', '.join(columns_to_select)} FROM {table_name}")
                
                for row in table_data:
                    # 텍스트 내용 결합
                    text_parts = []
                    for col in text_columns:
                        if row[col]:
                            text_parts.append(str(row[col]))
                    
                    if not text_parts:
                        continue
                        
                    text_content = " ".join(text_parts)
                    
                    try:
                        vector = self.embeddings.embed_query(text_content)
                        node_label = table_name.capitalize()
                        
                        # Neo4j에 벡터 저장
                        self.graph.query(f"""
                        MATCH (n:{node_label} {{{id_column}: {row[id_column]}}})
                        SET n.text_content = '{text_content.replace(chr(39), chr(92)+chr(39))}',
                            n.embedding = {vector}
                        """)
                        
                    except Exception as e:
                        print(f"   ⚠️ {table_name} {row[id_column]} 벡터 변환 실패: {e}")
                        continue
            
            print("✅ 텍스트 벡터 임베딩 완료!")
            
        except Exception as e:
            print(f"❌ 벡터 임베딩 실패: {e}")
            raise
    
    def create_vector_similarity_index(self):
        """벡터 유사도 검색을 위한 인덱스 생성"""
        try:
            print("🔄 벡터 인덱스 생성 중...")
            
            # 모든 노드 레이블 조회
            labels_result = self.graph.query("CALL db.labels()")
            labels = [label['label'] for label in labels_result if label['label'] not in ['Table', 'Column']]
            
            # 각 레이블에 대해 벡터 인덱스 생성
            for label in labels:
                try:
                    self.graph.query(f"""
                    CREATE VECTOR INDEX {label.lower()}_embeddings IF NOT EXISTS
                    FOR (n:{label}) ON n.embedding
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: 1024,
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """)
                except Exception as e:
                    print(f"   ⚠️ {label} 인덱스 생성 실패: {e}")
            
            print("✅ 벡터 인덱스 생성 완료!")
            
        except Exception as e:
            print(f"❌ 벡터 인덱스 생성 실패: {e}")
    
    def full_hybrid_embedding(self):
        """전체 하이브리드 임베딩 프로세스 실행"""
        try:
            print("🚀 하이브리드 데이터 임베딩 시작!")
            print("=" * 50)
            
            self.clear_neo4j_data()
            self.embed_schema_metadata()
            self.embed_actual_data()
            self.embed_text_vectors()
            self.create_vector_similarity_index()
            
            print("=" * 50)
            print("🎉 하이브리드 데이터 임베딩 완료!")
            
        except Exception as e:
            print(f"❌ 하이브리드 임베딩 실패: {e}")
            raise
    
    def get_embedding_stats(self):
        """임베딩 통계 정보 반환"""
        try:
            print("📊 임베딩 통계:")
            
            # 모든 노드 레이블과 개수
            labels_result = self.graph.query("""
            MATCH (n) 
            RETURN labels(n)[0] as label, count(n) as count 
            ORDER BY count DESC
            """)
            
            for item in labels_result:
                print(f"   {item['label']}: {item['count']}")
            
            # 벡터 임베딩 통계
            vector_stats = self.graph.query("""
            MATCH (n) 
            WHERE n.embedding IS NOT NULL 
            RETURN labels(n)[0] as label, count(n) as count
            """)
            
            if vector_stats:
                print("\n🔍 벡터 임베딩:")
                for item in vector_stats:
                    print(f"   {item['label']}: {item['count']}")
            
        except Exception as e:
            print(f"❌ 통계 조회 실패: {e}")
    
    def close_connections(self):
        """연결 종료"""
        try:
            if self.mariadb_conn:
                self.mariadb_conn.close()
                print("🔌 MariaDB 연결 종료")
        except Exception as e:
            print(f"⚠️ 연결 종료 중 오류: {e}")


def main():
    """데이터 임베더 실행"""
    neo4j_config = {
        'url': 'bolt://localhost:7687',
        'username': 'neo4j',
        'password': 'password123'
    }
    
    mariadb_config = {
        'host': 'localhost',
        'port': 32000,
        'user': 'genai',
        'password': 'genai1234',
        'database': 'llm_db_test',
        'charset': 'utf8mb4'
    }
    
    try:
        embedder = DataEmbedder(neo4j_config, mariadb_config, model_name="BAAI/bge-m3")
        embedder.full_hybrid_embedding()
        embedder.get_embedding_stats()
        embedder.close_connections()
        
    except Exception as e:
        print(f"❌ 실행 실패: {e}")


if __name__ == "__main__":
    main()