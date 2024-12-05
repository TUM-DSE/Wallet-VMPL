from abc import ABC, abstractmethod

def has_free_slot(node):
    for i in range(node.max_execution_slots):
        if node.execution_slots[i] == None:
            return True, i
    return False, 0

class Scheduler:
    @abstractmethod
    def pick_next_node(self, nodes, function):
        pass

class SimpleScheduler(Scheduler):
    def pick_next_node(self, nodes, function):
        cold_boot = False
        func_id = function.application_hash + function.func_hash
        for node in nodes:
            has_free, slot = has_free_slot(node)
            if has_free == False:
                continue
            # find a free node that has the function already registered
            # for a warm boot
            for i in range(node.max_functions):
                if (not node.function_slots_free[i]) and (node.functions_registered[i] == func_id):
                    cold_boot = False
                    return node, slot, cold_boot

        # there is no free node with this function registered, pick the first available node
        for node in nodes:
            has_free, slot = has_free_slot(node)
            if has_free == True:
                cold_boot = True
                return node, slot, cold_boot

        # there are no free nodes in the system!
        return None, 0, False

