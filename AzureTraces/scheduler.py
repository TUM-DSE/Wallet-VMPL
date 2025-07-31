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
        soft_warm = False
        soft_warm_node = None
        soft_warm_slot = 0
        cold_boot_node = None
        cold_boot_slot = 0
        func_id = function.application_hash + '-' +  function.func_hash
        for node in nodes:
            has_free, slot = has_free_slot(node)
            if has_free == False:
                continue

            if cold_boot_node == None:
                cold_boot_node = node
                cold_boot_slot = slot
            # find a free node that has the function already registered
            # for a warm boot
            for i in range(node.max_functions):
                if (not node.function_slots_free[i]) and (node.functions_registered[i] == func_id):
                    cold_boot = False
                    soft_warm = False
                    return node, slot, cold_boot, soft_warm

                # see if the node could be a soft warm
                if (not node.function_slots_free[i]) and (node.functions_registered[i].split('-')[0] == function.application_hash):
                    soft_warm_node = node
                    soft_warm_slot = slot

        # check if there was a warm node
        if soft_warm_node != None:
            # The old soft_warm system with a flat rate expect to turn a cold boot into a soft warm
            # Keeping the same logic for the dynamic soft warm as well just to more easilty integrate into the existing code
            # A bit messy but it is what it is
            soft_warm = True
            cold_boot = True
            return soft_warm_node, soft_warm_slot, cold_boot, soft_warm

        if cold_boot_node != None:
                cold_boot = True
                soft_warm = False
                return cold_boot_node, cold_boot_slot, cold_boot, soft_warm
            

        #OPTIMIZE: I can integrate this second for loop in the one above
        # there is no free node with this function registered, pick the first available node
       # for node in nodes:
       #     has_free, slot = has_free_slot(node)
       #     if has_free == True:
       #         cold_boot = True
       #         soft_warm = False
       #         return node, slot, cold_boot, soft_warm

        # there are no free nodes in the system!
        return None, 0, False, False

