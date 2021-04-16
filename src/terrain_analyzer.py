from queue import PriorityQueue
import math, pickle, os, hashlib, random
from player_controller import PlayerController

"""
PlatformScan, graph based least-visited-node-first traversal algorithm
Let map(V,E) be a directed cyclic graph
function traverse(from, to):
    from[to].visited = 1
    map[to].last_visit = 0
    for node in map:
        node.last_visit += 1
    need_reset = True
    for vert in from.vertices:
        if vert.visited == 0:
            need_reset = False
            break
    
    if need_reset:
        for vert in from.vertices:
            vert.visited = 0

function select(current_node):
    for vert in sorted(current_node.vertices, key=lambda x:vert.last_visit):
        if vert.visited = 0:
            return vert
"""

METHOD_DROP = "drop"
METHOD_TELEPORTU = "teleportup"
METHOD_TELEPORTJU = "teleportjup"
METHOD_TELEPORTD = "teleportd"
METHOD_TELEPORTJD = "teleportjd"
METHOD_TELEPORTL = "teleportl"
METHOD_TELEPORTR = "telerportr"
METHOD_DBLJMP_MAX = "dbljmp_max"
METHOD_DBLJMP_HALF = "dbljmp_half"
METHOD_DBLJMP = "dbljmp"
METHOD_JUMPR = "jumpr"
METHOD_JUMPL = "jumpl"
METHOD_MOVER = "movr"
METHOD_MOVEL = "movl"


class Platform:
    def __init__(self, start_x=None, start_y=None, end_x=None, end_y=None, last_visit=None, solutions=None, hash=None,
                 information=None):
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.last_visit = last_visit  # list of a list: [solution, 0]
        self.solutions = solutions
        self.information = information
        self.hash = hash

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)


class Solution:
    def __init__(self, from_hash=None, to_hash=None, lower_bound=None, upper_bound=None, method=None, visited=False):
        self.from_hash = from_hash
        self.to_hash = to_hash
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.method = method
        self.visited = visited

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)


class Information:
    def __init__(self, top_platforms=None, bottom_platforms=None, left_platforms=None, right_platforms=None):
        self.top_platforms = top_platforms
        self.bottom_platforms = bottom_platforms
        self.left_platforms = left_platforms
        self.right_platforms = right_platforms

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)


class AstarNode:
    def __init__(self, x=None, y=None, g=None, h=None, path=[]):
        self.x = x
        self.y = y
        self.g = g
        self.h = h
        self.f = 0
        self.path = path
        if self.g:
            self.f = self.g + self.h

    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)


class Node:
    def __init__(self, x=None, y=None, total_height=None):
        self.x = x
        self.y = y
        self.total_height = total_height
        self.neighbors = []
        self.isAPlatform = false

    def setIsPlatform(self, isPlatform=false):
        self.isPlatform = isPlatform

    def isPlatform(self):
        return self.isAPlatform

    def update_neighbors(self, otherNodes):
        self.neighbors = []

        if self.x < self.total_height - 1 and not otherNodes[self.y + 1][self.x].isPlatform():
            self.neighbors.append(otherNodes[self.y + 1][self.x])


class PathAnalyzer:
    """Converts minimap player coordinates to terrain information like ladders and platforms."""

    def __init__(self, mode="teleport"):
        """
        Difference between self.platforms and self.oneway_platforms: platforms can be a destination and an origin.
        However, oneway_platforms can only be an origin. oneway_platforms can be used to detect when player goes out of bounds.
        self.platforms: list of tuples, where tuple[0] is starting coordinate of platform, tuple[1] is end coordinate.

        """
        self.mode = "teleport"
        self.platforms = {}  # Format: hash, Platform()
        self.oneway_platforms = {}
        self.ladders = []
        self.visited_coordinates = []
        self.current_platform_coords = []
        self.current_oneway_coords = []
        self.current_ladder_coords = []
        self.last_x = None
        self.last_y = None
        self.movement = None

        self.platform_variance = 3  # If current pixel isn't in any pixel, if current x pixel within +- variance, include in platform
        self.ladder_variance = 2
        self.minimum_platform_length = 10  # Minimum x length of coordinates to be logged as a platform by input()
        self.minimum_ladder_length = 5  # Minimum y length of coordinated to be logged as a ladder by input()

        # below constants are used for generating solution graphs
        self.dbljump_max_height = 31  # total absolute jump height is about 31, but take account platform size
        self.jump_range = 16  # horizontal jump distance is about 9~10 EDIT:now using glide jump which has more range
        self.dbljump_half_height = 20  # absolute jump height of a half jump. Used for generating solution graph

        # below constants are used for path related algorithms.
        self.subplatform_length = 2  # length of subdivided platform

        self.astar_map_grid = []  # maap grid representation for a star graph search. reinitialized  on every call
        self.astar_open_val_grid = []  # 2d array to keep track of "open" values in a star search.
        self.astar_minimap_rect = []  # minimap rect (x,y,w,h) for use in generating astar data

    # def astar_pathfinds(self start_coord, goal_coords):

    def make_map_grid(self):
        map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]
        grid = []

        for height in range(map_height + 1):
            grid.append([0 for x in range(map_width + 1)])
        return grid

    # Temporarily here. Was moved from below
    def astar_findPath(self, start_coord, goal_coords):
        count = 0
        open_set = PriorityQueue()

        map_grid = self.make_map_grid()
        print(map_grid)

        # open_set.put((0, count, start_coord))
        # came_from = {}
        #
        # g_score = {spot: float("inf") for row in grid for spot in row}

    def astar_pathfind(self, start_coord, goal_coords):
        """
        Uses A* pathfinding to calculate a action map from start coord to goal.
        :param start_coord: start coordinate tuple for generating path
        :param goal_coords: goal coordinate
        :return: list of action tuple (g, a) where g is action goal coordinate tuple, a an action METHOD
        """
        self.astar_map_grid = []
        self.astar_open_val_grid = []
        map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]
        print(map_width, map_height)
        # Reinitialize map grid data (row and col)
        for height in range(map_height + 1):
            self.astar_map_grid.append([0 for x in range(map_width + 1)])
            self.astar_open_val_grid.append([0 for x in range(map_width + 1)])

        for key, platform in self.platforms.items():
            # currently this only uses the platform's start x and y coords and traces them until end x coords.
            # marks platform coordinate as 1
            for platform_coord in range(platform.start_x, platform.end_x + 1):
                self.astar_map_grid[platform.start_y][platform_coord] = 1

        # print('--------------------------------------')
        # print(start_coord[0], start_coord[1])

        open_list = set()
        closed_set = set()
        open_set = set()

        open_list.add(AstarNode(start_coord[0], start_coord[1], g=0, h=0))
        open_set.add(start_coord)

        while open_list:
            # get the lowest f(n) score in the open_list
            selection = min(open_list, key=lambda x: x.g + x.h)

            if selection.x == goal_coords[0] and selection.y == goal_coords[1]:
                # Already at destination
                return self.astar_optimize_path(selection.path)

            # Pop from list
            open_list.remove(selection)
            open_set.remove((selection.x, selection.y))
            closed_set.add((selection.x, selection.y))

            available_moves = self.astar_find_available_moves(selection.x, selection.y, goal_coords)
            for coordinate, method in available_moves:
                if coordinate in closed_set:
                    continue

                successor_g = selection.g + self.astar_g(selection.x, selection.y, coordinate[0], coordinate[1], method)
                successor_h = self.astar_h(coordinate[0], coordinate[1], goal_coords[0], goal_coords[1])
                successor_path = selection.path + [(coordinate, method)]
                if coordinate in open_set:
                    if self.astar_open_val_grid[coordinate[1]][coordinate[0]] < successor_g:
                        continue

                successor_node = AstarNode(coordinate[0], coordinate[1], g=selection.g + successor_g, h=successor_h,
                                           path=successor_path)
                open_list.add(successor_node)
                open_set.add(coordinate)

                if self.astar_open_val_grid[coordinate[1]][coordinate[0]] > successor_g:
                    self.astar_open_val_grid[coordinate[1]][coordinate[0]] = successor_g

    def astar_optimize_path(self, path):
        """
        Optimizes astar generated paths. This will take horizontal movement methods and combine them into one if on
        the same height.
        :param path: A* path list
        :return: optimized A* path list
        """
        new_path = []
        current_index = 0

        while current_index <= len(path) - 1:
            c_coords, c_method = path[current_index]
            if c_method == METHOD_MOVEL or c_method == METHOD_MOVER:
                increment = 0  # current_index + increment of intem we are sure needs to be optimized
                while current_index + increment < len(path) - 1:
                    n_coords, n_method = path[current_index + increment + 1]
                    if n_method == c_method and n_coords[1] == c_coords[1]:
                        increment += 1
                    else:
                        new_path.append(path[current_index + increment])
                        break
                current_index += increment + 1
            else:
                new_path.append(path[current_index])
                current_index += 1

        print("output")
        print(new_path)
        return new_path

    def distance(self, x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def astar_g(self, current_x, current_y, goal_x, goal_y, method):
        """
        generates A* g value
        :param current_x: x coordinate of current position
        :param current_y: y corodinate of current position
        :param goal_x: x coordinate of goal position
        :param goal_y: y coordinate of goal position
        :param method: find available moves method string
        :return: g value
        """
        if current_y == goal_y:
            return abs(current_x - goal_x)
        else:
            if current_y < goal_y:
                if method == METHOD_DROP:
                    return abs(current_y - goal_y) * 0.8
                if method == "horjmp":
                    return abs(current_y - goal_y) * 5
                return abs(current_y - goal_y) * 1.5
            elif current_y > goal_y:
                if method == "horjmp":
                    return abs(current_y - goal_y) * 5
                return abs(current_y - goal_y) * 1.2

    def astar_h(self, x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
        # return abs(x1-x2) + abs(y1-y2)

    def astar_find_available_moves(self, x, y, goal_coordinate):
        """
        Finds all the pixels which can be reached from (x,y). Methods include horizontal movement, jump and dropping
        :param x: x coord
        :param y: y coord
        :param goal_coordinate: goal coordinate tuple
        :return: list of tuples (coord, method) where coord is a coordinate tuple, method
        """
        map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]
        return_list = []

        # check horizontally touching pixels.
        for x_increment in [1, -1]:
            continue_check = True
            while continue_check:
                # if(x_increment > 0 and x_increment + x > goal_coordinate[0]):
                #     break
                # if(x_increment < 0 and x_increment + x < goal_coordinate[0]):
                #     break
                if x + x_increment == 0:
                    print('x + x_increment == 0')
                    return_list.append(((x + x_increment - 1, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                    break
                if -4 <= self.distance(x, y, goal_coordinate[0], goal_coordinate[1]) <= 8:
                    print('(x + x_increment, y) == goal_coordinate')
                    return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                    break
                if x + x_increment > map_width:
                    print('x + x_increment > map_width')
                    return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                    break
                if self.astar_map_grid[y][x + x_increment] == 1:
                    print('self.astar_map_grid[y][x + x_increment] == 1', y, x + x_increment,
                          self.astar_map_grid[y][x + x_increment])
                    drop_distance = 1
                    while y + drop_distance <= map_height:
                        if self.astar_map_grid[y + drop_distance][x] == 1:
                            return_list.append(
                                ((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                            continue_check = False
                            break
                        drop_distance += 1

                    for jmpheight in range(1, self.dbljump_max_height + 1):
                        if y - jmpheight <= 0:
                            break
                        if self.astar_map_grid[y - jmpheight][x + x_increment] == 1:
                            return_list.append(
                                ((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                            continue_check = False
                            break
                else:
                    if x_increment != 1:
                        return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                    break

                if x_increment < 0:
                    x_increment -= 1
                else:
                    x_increment += 1

        for jmpheight in range(1, self.dbljump_max_height):
            if y - jmpheight == 0:
                break
            if self.astar_map_grid[y - jmpheight][x] == 1:
                if self.mode == "teleport":
                    return_list.append(((x, y - jmpheight), METHOD_TELEPORTJU))
                else:
                    return_list.append(((x, y - jmpheight), METHOD_DBLJMP))

        drop_distance = 1
        while True:
            if y + drop_distance > map_height:
                break
            if self.astar_map_grid[y + drop_distance][x] == 1:
                return_list.append(((x, y + drop_distance), METHOD_DROP))
                break

            drop_distance += 1

        # check if horizontal doublejump leads us to another platform
        jump_height = 6

        return return_list

    def astar_jump_double_curve(self, start_x, start_y, current_x):
        """
        Calculates the height at horizontal double jump starting from(start_x, start_y) at x coord current_x
        :param start_x: start x coord
        :param start_y: start y coord
        :param current_x: x of coordinate to calculate height
        :return: height at current_x
        """
        slope = 0.05
        x_jump_range = 10 if current_x > start_x else -10
        y_jump_height = 1.4
        max_coord_x = (start_x * 2 + x_jump_range) / 2
        max_coord_y = start_y - y_jump_height
        if max_coord_y <= 0:
            return 0
        y = slope * (current_x - max_coord_x) ** 2 + max_coord_y
        return max(0, y)

    def save(self, filename="mapdata.platform", minimap_roi=None):
        """Save platforms, oneway_platforms, ladders, minimap_roi to a file
        :param filename: path to save file
        :param minimap_roi: tuple or list of onscreen minimap bounding box coordinates which will be saved"""
        with open(filename, "wb") as f:
            pickle.dump({"platforms": self.platforms, "oneway": self.oneway_platforms, "minimap": minimap_roi}, f)

    def load(self, filename="mapdata.platform"):
        """Open a map data file and load data from file. Also sets class variables platform, oneway_platform, and minimap.
        :param filename: Plath to map data file
        :return boundingRect tuple of minimap as stored on file (defaults to (x, y, w, h) if file is valid else 0"""
        if not self.verify_data_file(filename):
            return 0
        else:
            with open(filename, "rb") as f:
                data = pickle.load(f)
                self.platforms = data["platforms"]
                self.oneway_platforms = data["oneway"]
                minimap_coords = data["minimap"]
                self.astar_minimap_rect = minimap_coords

            self.generate_solution_dict()
            self.generate_platform_relations()

            self.astar_map_grid = []
            self.astar_open_val_grid = []
            map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]

            # Reinitialize map grid data
            for height in range(map_height + 1):
                self.astar_map_grid.append([0 for x in range(map_width + 1)])
                self.astar_open_val_grid.append([0 for x in range(map_width + 1)])
            for key, platform in self.platforms.items():
                # currently this only uses the platform's start x and y coords and traces them until end x coords.
                for platform_coord in range(platform.start_x, platform.end_x + 1):
                    self.astar_map_grid[platform.start_y][platform_coord] = 1
            return minimap_coords

    def verify_data_file(self, filename):
        """
        Verify a platform file to see if it is in correct format
        :param filename: file path
        :return: minimap coords if valid, 0 if corrupt or errored
        """
        if os.path.exists(filename):
            with open(filename, "rb") as f:
                try:
                    data = pickle.load(f)
                    platforms = data["platforms"]
                    oneway_platforms = data["oneway"]
                    minimap_coords = data["minimap"]
                except:
                    return 0
            return minimap_coords
        else:
            return 0

    def hash(self, data):
        """
        Returns salted md5 hash of data
        :param data: String to be hashed
        :return: hexdigest string MD5 hash
        """
        d_hash = hashlib.md5()
        d_hash.update((str(data) + str(random.random())).encode())
        return str(d_hash.hexdigest())[:8]

    def pathfind(self, start_hash, goal_hash):
        """
        Simple BFS algorithm to find a path from start platform to goal platform.
        :param start_hash: hash of starting platform
        :param goal_hash:  hash of goal platform
        :return: list, in order of solutions to reach goal, 0 if no path
        """
        try:
            start_platform = self.platforms[start_hash]
        except KeyError:
            start_platform = self.oneway_platforms[start_hash]
        # max_steps = len(self.platforms) + len(self.oneway_platforms) + 2
        calculated_paths = []
        bfs_queue = []
        visited_platform_hashes = []
        for solution in start_platform.solutions:
            if solution.to_hash not in visited_platform_hashes:
                bfs_queue.append([solution, [solution]])

        while bfs_queue:
            current_solution, paths = bfs_queue.pop()
            visited_platform_hashes.append(current_solution.from_hash)
            if current_solution.to_hash == goal_hash:
                calculated_paths.append(paths)
                break

            try:
                next_solution = self.platforms[current_solution.to_hash].solutions
            except KeyError:
                next_solution = self.oneway_platforms[current_solution.to_hash].solutions
            for solution in next_solution:
                if solution.to_hash not in visited_platform_hashes:
                    cv = paths
                    cv.append(solution)
                    bfs_queue.append([solution, cv])

        if calculated_paths:
            return sorted(calculated_paths, key=lambda x: len(x))[0]
        else:
            return 0

    def generate_solution_dict(self):
        """Generates a solution dictionary, which is a dictionary with platform as keys and a dictionary of a list[strategy, 0]
        This function is now called automatically within load()"""
        for key, platform in self.platforms.items():
            platform.last_visit = 0
            self.calculate_interplatform_solutions(key)
        for key, platform in self.oneway_platforms.items():
            self.calculate_interplatform_solutions(key, oneway=True)

    def move_platform(self, from_platform, to_platform):
        """Update navigation map visit counter to keep track of visited platforms when moded
        :param from_platform: departing platform hash
        :param to_platform: destination platform hash"""

        need_reset = True
        try:
            for method in self.platforms[from_platform].solutions:
                solution = method
                if solution.to_hash == to_platform:
                    self.platforms[solution.to_hash].last_visit = 0
                    method.visited = True

                else:
                    if not method.visited:
                        need_reset = False
        except:
            need_reset = False
            pass

        for key, platform in self.platforms.items():
            if key != to_platform and key != from_platform:
                self.platforms[key].last_visit += 1
        if need_reset:
            for method in self.platforms[from_platform].solutions:
                method.visited = False

    def select_move(self, current_platform):
        """
        Selects a solution from current_platform using PlatformScan
        :param current_platform: hash of departing platform
        :return: solution list in solution array of current_playform
        """
        try:
            for solution in sorted(self.platforms[current_platform].solutions,
                                   key=lambda x: self.platforms[x.to_hash].last_visit, reverse=True):
                """if not solution.visited:
                    return solution"""
                return solution
        except KeyError:
            for solution in sorted(self.oneway_platforms[current_platform].solutions,
                                   key=lambda x: self.platforms[x.to_hash].last_visit, reverse=True):
                """if not solution.visited:
                    return solution"""
                return solution

    def input_oneway_platform(self, inp_x, inp_y):
        """input values to use in finding one way(platforms which can't be a destination platform)
        Refer to input() to see how it works
        :param inp_x: x coordinate to log
        :param inp_y: y coordinate to log"""
        converted_tuple = (inp_x, inp_y)
        if converted_tuple not in self.visited_coordinates:
            self.visited_coordinates.append(converted_tuple)

        # check if in continous platform
        if inp_y >= self.last_y - 2 and inp_y <= self.last_y + 2 and self.last_x >= self.last_x - self.platform_variance and self.last_x <= self.last_x + self.platform_variance:
            # check if current coordinate is within platform being tracked
            if converted_tuple not in self.current_oneway_coords:
                self.current_oneway_coords.append(converted_tuple)
        else:
            # current coordinates do not belong in any platforms
            # terminate pending platform, if exists and create new pending platform
            if len(self.current_oneway_coords) >= self.minimum_platform_length - 1:
                platform_start = min(self.current_oneway_coords, key=lambda x: x[0])
                platform_end = max(self.current_oneway_coords, key=lambda x: x[0])
                d_hash = self.hash(str(platform_start))
                self.oneway_platforms[d_hash] = Platform(platform_start[0], platform_start[1], platform_end[0],
                                                         platform_end[1], 0, [], d_hash)
            self.current_oneway_coords = []
            if converted_tuple not in self.visited_coordinates:
                self.current_oneway_coords.append(converted_tuple)

    def flush_input_coords_to_platform(self, coord_list=None):
        if coord_list:
            self.current_platform_coords = coord_list
        if self.current_platform_coords:
            platform_start = min(self.current_platform_coords, key=lambda x: x[0])
            platform_end = max(self.current_platform_coords, key=lambda x: x[0])

            d_hash = self.hash(str(platform_start))
            self.platforms[d_hash] = Platform(platform_start[0], platform_start[1], platform_end[0], platform_end[1], 0,
                                              [], d_hash)
            self.current_platform_coords = []

    def flush_input_coords_to_oneway(self, coord_list=None):
        if coord_list:
            self.current_oneway_coords = coord_list
        if self.current_oneway_coords:
            platform_start = min(self.current_oneway_coords, key=lambda x: x[0])
            platform_end = max(self.current_oneway_coords, key=lambda x: x[0])

            d_hash = self.hash(str(platform_start))
            self.oneway_platforms[d_hash] = Platform(platform_start[0], platform_start[1], platform_end[0],
                                                     platform_end[1], 0,
                                                     [], d_hash)
            self.current_oneway_coords_coords = []

    def input(self, inp_x, inp_y):
        """Use player minimap coordinates to determine start and end of platforms
        This function logs player minimap marker coordinates in an attempt to identify platform coordinates from them.
        Player coordinates are temoporarily logged to self.current_platform_coords until a platform is determined for
        the given set of coordinates.
        Given that all platforms are parallel to the ground, meaning all coordinates of the platform are on the same
        elevation, a collection of input player coordinates are deemed to be on a same platform until a change in y
        coordinates is detected.
        :param inp_x: x player minimap coordinate to log
        :param inp_y: y player minimap coordinate to log"""
        converted_tuple = (inp_x, inp_y)
        if converted_tuple not in self.visited_coordinates:
            self.visited_coordinates.append(converted_tuple)

        # check if in continous platform
        if inp_y == self.last_y and self.last_x >= self.last_x - self.platform_variance and self.last_x <= self.last_x + self.platform_variance:
            # check if current coordinate is within platform being tracked
            if converted_tuple not in self.current_platform_coords:
                self.current_platform_coords.append(converted_tuple)
        else:
            # current coordinates do not belong in any platforms
            # terminate pending platform, if exists and create new pending platform
            if len(self.current_platform_coords) >= self.minimum_platform_length:
                platform_start = min(self.current_platform_coords, key=lambda x: x[0])
                platform_end = max(self.current_platform_coords, key=lambda x: x[0])

                d_hash = self.hash(str(platform_start))
                self.platforms[d_hash] = Platform(platform_start[0], platform_start[1], platform_end[0],
                                                  platform_end[1], 0, [], d_hash)

            self.current_platform_coords = []
            if converted_tuple not in self.visited_coordinates:
                self.current_platform_coords.append(converted_tuple)

        # check if in continous ladder
        if inp_x == self.last_x and inp_y >= self.last_y - self.ladder_variance and inp_y <= self.last_y + self.ladder_variance:
            # current coordinate is within pending group of coordinates for a ladder or a rope or whatever
            if converted_tuple not in self.current_ladder_coords:
                self.current_ladder_coords.append(converted_tuple)
        else:
            # current coordinates do not belong in any ladders or ropes
            # terminate ladder or ropes
            if len(self.current_ladder_coords) >= self.minimum_ladder_length:
                ladder_start = min(self.current_ladder_coords, key=lambda x: x[1])
                ladder_end = max(self.current_ladder_coords, key=lambda x: x[1])
                self.ladders.append((ladder_start, ladder_end))
            self.current_ladder_coords = []
            if converted_tuple not in self.visited_coordinates:
                self.current_ladder_coords.append(converted_tuple)
        self.last_x = inp_x
        self.last_y = inp_y

    def calculate_interplatform_solutions(self, hash, oneway=False):
        """Find relationships between platform, like how one platform links to another using movement.
        :param platform : platform hash in self.platforms Platform
        :return : None
        destination_platform : platform object in self.platforms which is the destination
        x, y : coordinate area where the method can be used (x1<=coord_x<=x2, y1<=coord_y<=y2)
        method : movement method string
            drop : drop down directly
            jmpr : right jump
            jmpl : left jump
            dbljmp_max : double jump up fully
            dbljmp_half : double jump a bit less
        """

        if oneway:
            platform = self.oneway_platforms[hash]
        else:
            platform = self.platforms[hash]

        platform.solutions = []

        for key, other_platform in self.platforms.items():
            if platform.hash != key:
                # 1. Detect vertical overlaps
                if platform.start_x < other_platform.end_x and platform.end_x > other_platform.start_x or \
                        platform.start_x > other_platform.start_x and platform.start_x < other_platform.end_x:
                    lower_bound_x = max(platform.start_x, other_platform.start_x)
                    upper_bound_x = min(platform.end_x, other_platform.end_x)
                    if platform.start_y < other_platform.end_y:
                        # Platform is higher than current_platform. Thus we can just drop
                        # solution = {"hash":key, "lower_bound":(lower_bound_x, platform.start_y), "upper_bound":(upper_bound_x, platform.start_y), "method":"drop", "visited" : False}
                        solution = Solution(platform.hash, key, (lower_bound_x, platform.start_y),
                                            (upper_bound_x, platform.start_y), METHOD_DROP, False)
                        # Changed to using classes for readability
                        platform.solutions.append(solution)
                    else:
                        # We need to use double jump to get there, but first check if within jump height
                        if abs(platform.start_y - other_platform.start_y) <= self.dbljump_half_height:
                            # solution = {"hash":key, "lower_bound":(lower_bound_x, platform.start_y), "upper_bound":(upper_bound_x, platform.start_y), "method":"dbljmp_half", "visited" : False}
                            if self.mode == "teleport":
                                solution = Solution(platform.hash, key, (lower_bound_x, platform.start_y),
                                                    (upper_bound_x, platform.start_y), METHOD_TELEPORTU, False)
                            else:
                                solution = Solution(platform.hash, key, (lower_bound_x, platform.start_y),
                                                    (upper_bound_x, platform.start_y), METHOD_DBLJMP_HALF, False)
                            platform.solutions.append(solution)
                        elif abs(platform.start_y - other_platform.start_y) <= self.dbljump_max_height:
                            # solution = {"hash": key, "lower_bound": (lower_bound_x, platform.start_y),"upper_bound": (upper_bound_x, platform.start_y), "method": "dbljmp_max", "visited" : False}
                            if self.mode == "teleport":
                                solution = Solution(platform.hash, key, (lower_bound_x, platform.start_y),
                                                    (upper_bound_x, platform.start_y), METHOD_TELEPORTJU, False)
                            else:
                                solution = Solution(platform.hash, key, (lower_bound_x, platform.start_y),
                                                    (upper_bound_x, platform.start_y), METHOD_DBLJMP_MAX, False)
                            platform.solutions.append(solution)
                else:
                    # 2. No vertical overlaps. Calculate euclidean distance between each platform endpoints
                    front_point_distance = math.sqrt(
                        (platform.start_x - other_platform.end_x) ** 2 + (platform.start_y - other_platform.end_y) ** 2)
                    if front_point_distance <= self.jump_range:
                        # We can jump from the left end of the platform to goal
                        # solution = {"hash":key, "lower_bound":(platform.start_x, platform.start_y), "upper_bound":(platform.start_x, platform.start_y), "method":"jmpl", "visited" : False}
                        solution = Solution(platform.hash, key, (platform.start_x, platform.start_y),
                                            (platform.start_x, platform.start_y), METHOD_JUMPL, False)
                        platform.solutions.append(solution)

                    back_point_distance = math.sqrt(
                        (platform.end_x - other_platform.start_x) ** 2 + (platform.end_y - other_platform.start_y) ** 2)
                    if back_point_distance <= self.jump_range:
                        # We can jump fomr the right end of the platform to goal platform
                        # solution = {"hash":key, "lower_bound":(platform.end_x, platform.end_y), "upper_bound":(platform.end_x, platform.end_y), "method":"jmpr", "visited" : False}
                        solution = Solution(platform.hash, key, (platform.end_x, platform.end_y),
                                            (platform.end_x, platform.end_y), METHOD_JUMPR, False)
                        platform.solutions.append(solution)

    def generate_platform_relations(self):
        platforms = self.platforms.items()
        # [('7b54fabe', <terrain_analyzer.Platform object at 0x0000027FC67EF550>), ('6521b24c', <terrain_analyzer.Platform object at 0x0000027FC67EF520>)>
        """"""
        sorted_platforms_with_y = sorted(platforms, key=lambda k: k[1].end_y, reverse=True)  # list

        platform_hashes = list(map(lambda x: x[0], sorted_platforms_with_y))

        for index, curr_hash in enumerate(platform_hashes):
            curr_plat_data = self.platforms[curr_hash]

            """
            Get a list of overlapping platform for current platform (up down left right)
            """
            overlapping_platforms = (list(filter(lambda x: (
                    curr_hash is not x[0] and \
                    curr_plat_data.start_x < x[1].end_x and curr_plat_data.end_x > x[1].start_x or \
                    curr_plat_data.start_x > x[1].start_x and curr_plat_data.start_x < x[1].end_x
            ), sorted_platforms_with_y)))

            top_platforms = []
            bottom_platforms = []
            left_platforms = []
            right_platforms = []
            selected_top_platform = None  # Used to track if there exist another platform horizontally on the same Y axis (w/ offset)
            selected_btm_platform = None  # Used to track if there exist another platform horizontally on the same Y axis (w/ offset)
            selected_left_platform = None  # Used to track if there exist another left platform within jump and fall range
            selected_right_platform = None  # Used to track if there exist another left platform within jump and fall range
            allowed_horizontal_plat_Y_offset = 10

            """Get platforms above"""
            for curr_overlap_plat in overlapping_platforms:
                # curr_overlap_plat is a tuple with [0] -> hash, [1] -> PlatformAnalyzer object
                curr_overlap_plat_data = curr_overlap_plat[1]

                if curr_overlap_plat_data.end_y < curr_plat_data.start_y:
                    if not selected_top_platform or curr_overlap_plat_data.end_y == selected_top_platform[1].end_y:
                        selected_top_platform = curr_overlap_plat
                        top_platforms.append(selected_top_platform)

            """Get platforms below"""
            overlapping_platforms.reverse()
            for curr_overlap_plat in overlapping_platforms:
                # curr_overlap_plat is a tuple with [0] -> hash, [1] -> PlatformAnalyzer object
                curr_overlap_plat_data = curr_overlap_plat[1]

                if curr_overlap_plat_data.end_y > curr_plat_data.start_y:
                    if not selected_btm_platform or curr_overlap_plat_data.end_y == selected_btm_platform[1].end_y:
                        selected_btm_platform = curr_overlap_plat
                        bottom_platforms.append(selected_btm_platform)

            """Get left platforms"""
            for platform in sorted_platforms_with_y:
                platform_hash = platform[0]
                platform_data = platform[1]

                if curr_hash is not platform_hash:
                    """
                    Condition
                    1) Comparing platform must have end x lesser than current start x
                    2) Lower comparing platform must exceed -10 difference in Y coordinate for char to jumpa and fall
                    3) Higher comparing platform must be within 9 jump distance of Y to allow jumps
                    4) Comparing platform cannot be horizontally further than char by defined teleport/flashjump distance
                    """

                    if platform_data.end_x < curr_plat_data.start_x and \
                            (curr_plat_data.start_y - platform_data.end_y >= -10
                             and curr_plat_data.start_y - platform_data.end_y <= 5) and \
                            platform_data.start_x - curr_plat_data.end_x <= 15:
                        selected_left_platform = platform
                        left_platforms.append(selected_left_platform)

            """Get right platforms"""
            for platform in sorted_platforms_with_y:
                platform_hash = platform[0]
                platform_data = platform[1]

                if curr_hash is not platform_hash:
                    """
                    Condition
                    1) Comparing platform must have start x higher than current end x
                    2) Lower comparing platform must exceed -20 difference in Y coordinate for char to jumpa and fall
                    3) Higher comparing platform must be within 9 jump distance of Y to allow jumps
                    4) Comparing platform cannot be horizontally further than char by defined teleport/flashjump distance
                    """

                    if curr_plat_data.end_x < platform_data.start_x and \
                            (curr_plat_data.start_y - platform_data.end_y >= -10
                             and curr_plat_data.start_y - platform_data.end_y <= 5) and \
                            curr_plat_data.start_x - platform_data.end_x <= 15:
                        selected_right_platform = platform
                        right_platforms.append(selected_right_platform)

            information = Information(top_platforms, bottom_platforms, left_platforms, right_platforms)
            self.platforms[curr_hash].information = information
            # print(self.platforms[curr_hash].information)


def astar_pathfind(self, start_coord, goal_coords):
    """
    Uses A* pathfinding to calculate a action map from start coord to goal.
    :param start_coord: start coordinate tuple for generating path
    :param goal_coords: goal coordinate
    :return: list of action tuple (g, a) where g is action goal coordinate tuple, a an action METHOD
    """
    self.astar_map_grid = []
    self.astar_open_val_grid = []
    map_width, x = self.astar_minimap_rect[2], self.astar_minimap_rect[3]

    # Reinitialize map grid data
    for height in range(map_height + 1):
        self.astar_map_grid.append([0 for x in range(map_width + 1)])
        self.astar_open_val_grid.append([0 for x in range(map_width + 1)])

    for key, platform in self.platforms.items():
        # currently this only uses the platform's start x and y coords and traces them until end x coords.
        for platform_coord in range(platform.start_x, platform.end_x + 1):
            self.astar_map_grid[platform.start_y][platform_coord] = 1
    print('--------------------------------------')
    print(start_coord[0])
    print(start_coord[1])
    open_list = set()
    closed_set = set()
    open_set = set()
    open_list.add(AstarNode(start_coord[0], start_coord[1], g=0, h=0))
    open_set.add(start_coord)

    while open_list:
        selection = min(open_list, key=lambda x: x.g + x.h)

        if selection.x == goal_coords[0] and selection.y == goal_coords[1]:
            return self.astar_optimize_path(selection.path)
        # print('selection: %s', selection)

        open_list.remove(selection)
        open_set.remove((selection.x, selection.y))
        closed_set.add((selection.x, selection.y))
        for coordinate, method in self.astar_find_available_moves(selection.x, selection.y, goal_coords):
            if coordinate in closed_set:
                continue
            successor_g = selection.g + self.astar_g(selection.x, selection.y, coordinate[0], coordinate[1], method)
            successor_h = self.astar_h(coordinate[0], coordinate[1], goal_coords[0], goal_coords[1])
            successor_path = selection.path + [(coordinate, method)]
            if coordinate in open_set:
                if self.astar_open_val_grid[coordinate[1]][coordinate[0]] < successor_g:
                    continue

            successor_node = AstarNode(coordinate[0], coordinate[1], g=selection.g + successor_g, h=successor_h,
                                       path=successor_path)
            open_list.add(successor_node)
            open_set.add(coordinate)
            if self.astar_open_val_grid[coordinate[1]][coordinate[0]] > successor_g:
                self.astar_open_val_grid[coordinate[1]][coordinate[0]] = successor_g


def astar_optimize_path(self, path):
    """
    Optimizes astar generated paths. This will take horizontal movement methods and combine them into one if on
    the same height.
    :param path: A* path list
    :return: optimized A* path list
    """
    print("input")
    print(path)
    new_path = []
    current_index = 0
    while current_index <= len(path) - 1:
        c_coords, c_method = path[current_index]
        if c_method == METHOD_MOVEL or c_method == METHOD_MOVER:
            increment = 0  # current_index + increment of intem we are sure needs to be optimized
            while current_index + increment < len(path) - 1:
                n_coords, n_method = path[current_index + increment + 1]
                if n_method == c_method and n_coords[1] == c_coords[1]:
                    increment += 1
                else:
                    new_path.append(path[current_index + increment])
                    break
            current_index += increment + 1
        else:
            new_path.append(path[current_index])
            current_index += 1

    print("output")
    print(new_path)
    return new_path


def astar_g(self, current_x, current_y, goal_x, goal_y, method):
    """
    generates A* g value
    :param current_x: x coordinate of current position
    :param current_y: y corodinate of current position
    :param goal_x: x coordinate of goal position
    :param goal_y: y coordinate of goal position
    :param method: find available moves method string
    :return: g value
    """
    if current_y == goal_y:
        return abs(current_x - goal_x)
    else:
        if current_y < goal_y:
            if method == METHOD_DROP:
                return abs(current_y - goal_y) * 0.8
            if method == "horjmp":
                return abs(current_y - goal_y) * 5
            return abs(current_y - goal_y) * 1.5
        elif current_y > goal_y:
            if method == "horjmp":
                return abs(current_y - goal_y) * 5
            return abs(current_y - goal_y) * 1.2


def astar_h(self, x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    # return abs(x1-x2) + abs(y1-y2)


def astar_find_available_moves(self, x, y, goal_coordinate):
    """
    Finds all the pixels which can be reached from (x,y). Methods include horizontal movement, jump and dropping
    :param x: x coord
    :param y: y coord
    :param goal_coordinate: goal coordinate tuple
    :return: list of tuples (coord, method) where coord is a coordinate tuple, method
    """
    map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]
    return_list = []
    # check horizontally touching pixels.
    for x_increment in [1, -1]:
        contiunue_check = True
        while contiunue_check:
            if x + x_increment == 0:
                return_list.append(((x + x_increment - 1, y), METHOD_MOVER if x_increment > 0 else "l"))
                break
            if (x + x_increment, y) == goal_coordinate:
                return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                break
            if x + x_increment > map_width:
                return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                break
            if self.astar_map_grid[y][x + x_increment] == 1:
                drop_distance = 1
                while y + drop_distance <= map_height:
                    if self.astar_map_grid[y + drop_distance][x] == 1:
                        return_list.append(
                            ((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                        contiunue_check = False
                        break
                    drop_distance += 1

                for jmpheight in range(1, self.dbljump_max_height + 1):
                    if y - jmpheight <= 0:
                        break
                    if self.astar_map_grid[y - jmpheight][x + x_increment] == 1:
                        return_list.append(
                            ((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                        contiunue_check = False
                        break
            else:
                if x_increment != 1:
                    return_list.append(((x + x_increment, y), METHOD_MOVER if x_increment > 0 else METHOD_MOVEL))
                break

            if x_increment < 0:
                x_increment -= 1
            else:
                x_increment += 1

    for jmpheight in range(1, self.dbljump_max_height):
        if y - jmpheight == 0:
            break
        if self.astar_map_grid[y - jmpheight][x] == 1:
            if self.mode == "teleport":
                return_list.append(((x, y - jmpheight), METHOD_TELEPORTJU))
            else:
                return_list.append(((x, y - jmpheight), METHOD_DBLJMP))

    drop_distance = 1
    while True:
        if y + drop_distance > map_height:
            break
        if self.astar_map_grid[y + drop_distance][x] == 1:
            return_list.append(((x, y + drop_distance), METHOD_DROP))
            break

        drop_distance += 1

    # check if horizontal doublejump leads us to another platform
    jump_height = 6

    return return_list


def astar_jump_double_curve(self, start_x, start_y, current_x):
    """
    Calculates the height at horizontal double jump starting from(start_x, start_y) at x coord current_x
    :param start_x: start x coord
    :param start_y: start y coord
    :param current_x: x of coordinate to calculate height
    :return: height at current_x
    """
    slope = 0.05
    x_jump_range = 10 if current_x > start_x else -10
    y_jump_height = 1.4
    max_coord_x = (start_x * 2 + x_jump_range) / 2
    max_coord_y = start_y - y_jump_height
    if max_coord_y <= 0:
        return 0
    y = slope * (current_x - max_coord_x) ** 2 + max_coord_y
    return max(0, y)


def calculate_vertical_doublejump_delay(self, y1, y2):
    """
    Calcuates the delay needed to double jump from height y1 to y1
    :param y1: y coord1
    :param y2: y coord2
    :return: float delay in second(s) needed
    """
    height_delta = abs(y1 - y2)

    t = round(-(height_delta - 41.5) / 76, 2)
    if t < 0.15:
        return 0.15
    elif t > 0.45:
        return 0.45
    else:
        return t


def reset(self):
    """
    Reset all platform data to default
    :return: None
    """
    self.platforms = {}
    self.oneway_platforms = {}
    self.visited_coordinates = []
    self.current_platform_coords = []
    self.current_ladder_coords = []
    self.ladders = []

# def get_platform_information(self, oneway=False):
#     platforms = self.platforms.items()
#     # [('7b54fabe', <terrain_analyzer.Platform object at 0x0000027FC67EF550>), ('6521b24c', <terrain_analyzer.Platform object at 0x0000027FC67EF520>), ('9d418e58', <terrain_analyzer.Platform object at 0x0000027FC67EF460>), ('4bcf1a36', <terrain_analyzer.Platform object at 0x0000027FC67EF490>), ('d999bf89', <terrain_analyzer.Platform object at 0x0000027FC67EF4C0>)] <class 'list'>
#     sorted_platforms_with_y = sorted(platforms, key=lambda k: k[1].end_y, reverse=True)  # list
#
#     platform_hashes = list(map(lambda x: x[0], sorted_platforms_with_y))
#
#     for index, hash in enumerate(platform_hashes):
#         current_platform_data = self.platforms[hash]
#         current_platform_data.information = []
#
#         # Storing possible top platform
#         platform_above = None
#         hash_of_next_platform = None
#
#         for innerIndex, innerHash in enumerate(platform_hashes):
#             if innerHash != hash:
#
#                 if index != len(platform_hashes) - 1:
#                     hash_of_next_platform = platform_hashes[innerIndex + 1]
#
#                 # Initialize next platform with next in list (since already sorted by y)
#                 # Technically if a platform has the highest Y axis means there will be no platform above it
#
#                 if hash_of_next_platform and hash != hash_of_next_platform and innerIndex > index:
#                     platform_above = (list(filter(lambda x: x[0] == hash_of_next_platform, sorted_platforms_with_y)))[0]
#
#                     # Check if next platform is horizontally on top of current platform
#                     next_platform_data = platform_above[1]
#                     # print('next possible: ', 'hash:', 'Coord:', next_platform_data.start_x, next_platform_data.end_x)
#                     # current_platform_data = current_platform[1]
#                     print('Comparing', hash, hash_of_next_platform)
#                     print('current', current_platform_data.start_x, current_platform_data.end_x)
#                     if (
#                             max(current_platform_data.end_x, next_platform_data.end_x) - min(current_platform_data.start_x, next_platform_data.start_x) < (current_platform_data.end_x - current_platform_data.start_x) + (next_platform_data.end_x - next_platform_data.start_x)
#                     ):
#                         print('next plat: ', 'Coord:', next_platform_data.start_x, next_platform_data.end_x)
#                         hash_of_next_platform = innerHash
#                         break
#                         """
#                         # Top platform is located slightly right to current platform
#                             ------- Top
#                         ------- Current
#                         """
#
#                         """
#                         # Top platform is location left to current platform
#                         ------- Top
#                            -------- Current
#                         """
#
#                         """
#                         # Top platform is longer than current platform in left and right direction
#                         ----------- Top
#                             ----   Current
#                         """
#
#                         """
#                         # Top platform is shorter than current platform in left and right direction
#                             ----   Top
#                         ----------- Current
#                         """
#                 else:
#                     hash_of_next_platform = None
