from collections import Counter

def _has_cycle(task_map):
    visited = set()
    stack = set()
    def dfs(node_id):
        if node_id in stack:
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        stack.add(node_id)
        for dep in task_map.get(node_id, {}).get("dependencies",[]):
            if dep in task_map and dfs(dep):
                return True
        stack.remove(node_id)
        return False
    return any(dfs(task_id) for task_id in task_map)

def calculate_risk(handoff_dict: dict) -> dict:
    score = 0
    reasons = []
    
    tasks = handoff_dict.get("tasks",[])
    task_count = len(tasks)
    
    if task_count == 0:
        score += 50
        reasons.append("no_tasks")
    elif task_count > 10:
        score += 30
        reasons.append("too_many_tasks")
    elif task_count < 3:
        score += 15
        reasons.append("too_few_tasks")
        
    if task_count > 0:
        empty_ac_count = sum(1 for t in tasks if len(t.get("acceptance_criteria",[])) == 0)
        if empty_ac_count > 0:
            score += min(30, empty_ac_count * 10)
            reasons.append("missing_acceptance_criteria")
            
    ids = [t.get("id") for t in tasks if t.get("id")]
    id_set = set(ids)
    undefined_deps = 0
    owner_counter = Counter()
    task_map = {}
    
    for t in tasks:
        tid = t.get("id")
        if tid:
            task_map[tid] = t
        owner = t.get("owner")
        if owner:
            owner_counter[owner] += 1
        for dep in t.get("dependencies",[]):
            if dep not in id_set:
                undefined_deps += 1
                
    if undefined_deps > 0:
        score += min(20, undefined_deps * 5)
        reasons.append("undefined_dependencies")
        
    if task_map and _has_cycle(task_map):
        score += 25
        reasons.append("dependency_cycle")
        
    if owner_counter:
        major_owner_ratio = max(owner_counter.values()) / task_count
        if major_owner_ratio >= 0.8 and task_count >= 5:
            score += 10
            reasons.append("owner_imbalance")
            
    tech_stack = handoff_dict.get("tech_stack", {})
    if tech_stack.get("status") == "pending":
        score += 20
        reasons.append("tech_stack_pending")
        
    return {"score": min(score, 100), "reasons": reasons}
