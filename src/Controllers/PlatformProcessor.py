import math, pickle, os, hashlib, random, sys

from ..player_controller import PlayerController

class Platform:
    def __init__(self, start_x=None, start_y=None, end_x=None, end_y=None, last_visit=None, solutions=None, hash=None, platform_type=None, info=None):
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.last_visit = last_visit  # list of a list: [solution, 0]
        self.solutions = solutions
        self.hash = hash
        self.platform_type = platform_type
        self.info = info

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

class Information:
    def __init__(self, platform_above=None):
        self.platform_above = platform_above

class PathAnalyzer:
    """Converts minimap player coordinates to terrain information like ladders and platforms."""

    def __init__(self, mode="teleport"):
        self.platforms = {}  # Format: hash, Platform()
        self.astar_map_grid = []  # map grid representation for a star graph search. reinitialized  on every call
        self.astar_open_val_grid = []  # 2d array to keep track of "open" values in a star search.
        self.astar_minimap_rect = []  # minimap rect (x,y,w,h) for use in generating astar data

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
                    minimap_coords = data["minimap"]
                except:
                    return 0
            return minimap_coords
        else:
            return 0

    def save(self, filename="mapdata.platform", minimap_roi=None):
        """
        Save platforms, oneway_platforms, ladders, minimap_roi to a file
        :param filename: path to save file
        :param minimap_roi: tuple or list of onscreen minimap bounding box coordinates which will be saved
        """
        with open(filename, "wb") as f:
            pickle.dump({"platforms": self.platforms, "minimap": minimap_roi}, f)

    def load(self, filename="mapdata.platform"):
        """
        Open a map data file and load data from file. Also sets class variables platform, and minimap.
        :param filename: Path to map data file
        :return boundingRect tuple of minimap as stored on file (defaults to (x, y, w, h) if file is valid else 0
        """
        if not self.verify_data_file(filename):
            return 0
        else:
            with open(filename, "rb") as f:
                data = pickle.load(f)
                self.platforms = data["platforms"]
                minimap_coords = data["minimap"]
                self.astar_minimap_rect = minimap_coords

            self.generate_solution_dict()
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

    def platforms_overlap(self, current_platform, other_platform):
        if current_platform.start_x < other_platform.end_x and current_platform.end_x > other_platform.start_x or \
                current_platform.start_x > other_platform.start_x and current_platform.start_x < other_platform.end_x:
            return True
        return False

    def generate_solution_dict(self):
        """
        Generates a solution dictionary, which is a dictionary with platform as keys and a dictionary of a list[strategy, 0]
        This function is now called automatically within load()
        """
        for key, platform in self.platforms.items():
            platform.last_visit = 0
            self.calculate_interplatform_solutions(key)
        # for key, platform in self.oneway_platforms.items():
        #     self.calculate_interplatform_solutions(key, oneway=True)

    def get_platform_relations(self):
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
                curr_hash is not x[0] and
                curr_plat_data.start_x < x[1].end_x and curr_plat_data.end_x > x[1].start_x or
                curr_plat_data.start_x > x[1].start_x and curr_plat_data.start_x < x[1].end_x
            ), sorted_platforms_with_y)))

            top_platforms = []
            bottom_platforms = []
            left_platforms = []
            right_platforms = []
            selected_top_platform = None # Used to track if there exist another platform horizontally on the same Y axis (w/ offset)
            selected_btm_platform = None # Used to track if there exist another platform horizontally on the same Y axis (w/ offset)
            selected_left_platform = None # Used to track if there exist another left platform within jump and fall range
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
                        (-10 <= curr_plat_data.start_y - platform_data.end_y <= 5) and \
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
                            (-10 <= curr_plat_data.start_y - platform_data.end_y <= 5) and \
                            curr_plat_data.start_x - platform_data.end_x <= 15:
                        selected_right_platform = platform
                        right_platforms.append(selected_right_platform)

            information = Information(top_platforms, bottom_platforms, left_platforms, right_platforms)
            self.platforms[curr_hash].information = information

    def astar_pathfind(self, start_coord, goal_coords):
        """
        Uses A* pathfinding to calculate a action map from start coord to goal.
        :param start_coord: start coordinate tuple for generating path (player.x, player.y)
        :param goal_coords: goal coordinate ((x1, x2), y1)
        :return: list of action tuple (g, a) where g is action goal coordinate tuple, a an action METHOD
        """

        self.astar_map_grid = []
        self.astar_open_val_grid = []
        map_width, map_height = self.astar_minimap_rect[2], self.astar_minimap_rect[3]

        # Reinitialize map grid data
        for height in range(map_height + 1):
            self.astar_map_grid.append([0 for x in range(map_width + 1)])
            self.astar_open_val_grid.append([0 for x in range(map_width + 1)])

