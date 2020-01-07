import gc
from typing import List
from snowshu.configs import MAX_ALLOWED_ROWS
from snowshu.core.compile import RuntimeSourceCompiler
from snowshu.adapters.target_adapters.base_target_adapter import BaseTargetAdapter
from snowshu.adapters.source_adapters.base_source_adapter import BaseSourceAdapter
import networkx as nx
from snowshu.logger import Logger, duration
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

logger=Logger().logger

@dataclass
class GraphExecutable:
    graph:nx.Graph
    source_adapter:BaseSourceAdapter
    target_adapter:BaseTargetAdapter
    analyze:bool
        

class GraphSetRunner:

    def execute_graph_set(  self,
                            graph_set:List[nx.Graph],
                            source_adapter:BaseSourceAdapter,
                            target_adapter:BaseTargetAdapter,
                            threads:int,
                            analyze:bool=False)->None:
        
        executables=[GraphExecutable(   graph,
                                        source_adapter,
                                        target_adapter,
                                        analyze) for graph in graph_set]

        start_time=time.time()
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            for executable in executables:
                executor.submit(self._traverse_and_execute,executable,start_time)
    
    def _traverse_and_execute(self,executable:GraphExecutable,start_time:int)->None:
        try:
            logger.debug(f"Executing graph with {len(executable.graph)} relations in it...")
            for i,relation in enumerate(nx.algorithms.dag.topological_sort(executable.graph)):
                logger.info(f'Executing graph {i+1} of {len(executable.graph)} source query for relation {relation.dot_notation}...')
                relation=RuntimeSourceCompiler.compile_queries_for_relation(relation,
                                                                            executable.graph,
                                                                            executable.source_adapter,
                                                                            executable.analyze)
                if executable.analyze:
                    result=[row for row in executable.source_adapter.check_count_and_query(relation.compiled_query,MAX_ALLOWED_ROWS).itertuples()][0]
                    relation.population_size=result.population_size
                    relation.sample_size=result.sample_size
                    logger.info(f'Analysis of relation {relation.dot_notation} completed in {duration(start_time)}.')        
                else:
                    ##stage target
                    logger.info(f'Retrieving records from source {relation.dot_notation}...')        
                    relation.database=executable.target_adapter.create_database_if_not_exists(relation.database)
                    executable.target_adapter.create_schema_if_not_exists(relation.database,relation.schema)
                    try:
                        relation.data=executable.source_adapter.check_count_and_query(relation.compiled_query,MAX_ALLOWED_ROWS)
                    except Exception as e:
                        raise SystemError(f'Failed execution of extraction sql statement: {relation.compiled_query}')
                        
                    relation.population_size=0 #TODO:fix this!
                    relation.sample_size=len(relation.data)
                    logger.info(f'{relation.sample_size} records retrieved for relation {relation.dot_notation}. Inserting into target...')
                    try:
                        executable.target_adapter.create_and_load_relation(relation)
                    except Exception as e:
                        raise SystemError(f'Failed execution of sql load statement: {relation.compiled_query}')

                    logger.info(f'Done replication of relation {relation.dot_notation} in {duration(start_time)}.')        
                    relation.target_loaded=True
                relation.source_extracted=True
                logger.info(f'population:{relation.population_size}, sample:{relation.sample_size}')
            try:
                for relation in executable.graph.nodes:
                    del relation.data
            except AttributeError:
                pass
            gc.collect()       
        except Exception as e:
            logger.error(f'failed with error of type {type(e)}: {str(e)}')
            raise e
