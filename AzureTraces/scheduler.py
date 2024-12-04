from abc import ABC, abstractmethod

class Scheduler:
    @abstractmethod
    def pick_next_node(self, nodes, function):
        pass

class SimpleScheduler(Scheduler):
    def pick_next_node(self, nodes, function):
        cold_boot = False
        func_id = function.application_hash + function.func_hash
        for node in nodes:
            if node.curr_function != None:
                continue
            # find a free node that has the function already registered
            # for a warm boot
            for i in range(node.max_functions):
                if (not node.function_slots_free[i]) and (functions[i] == func_id):
                    cold_boot = False
                    return node, cold_boot

        # there is no free node with this function registered, pick the first available node
        for node in nodes:
            if node.curr_function == None:
                cold_boot = True
                return node, cold_boot

        # there are no free nodes in the system!
        return None, False

