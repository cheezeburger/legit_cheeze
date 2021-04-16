import keystate_manager as km
import player_controller as pc
import screen_processor as sp
import terrain_analyzer as ta
import directinput_constants as dc
import rune_solver as rs
import logging, math, time, random
from screen_processor import MapleScreenCapturer


class CustomLogger:
    def __init__(self, logger_obj, logger_queue):
        self.logger_obj = logger_obj
        self.logger_queue = logger_queue

    def debug(self, *args):
        self.logger_obj.debug(" ".join([str(x) for x in args]))
        if self.logger_queue:
            self.logger_queue.put(("log", " ".join([str(x) for x in args])))

    def exception(self, *args):
        self.logger_obj.exception(" ".join([str(x) for x in args]))
        if self.logger_queue:
            self.logger_queue.put(("log", " ".join([str(x) for x in args])))


class BaseScript:
    def __init__(self, keymap=km.DEFAULT_KEY_MAP, log_queue=None):
        # Maple handler and Loggger
        self.screen_capturer = sp.MapleScreenCapturer()
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(logging.DEBUG)
        self.log_queue = log_queue
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler("logging.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        self.logger = CustomLogger(logger, self.log_queue)
        self.logger.debug("%s init" % self.__class__.__name__)

        self.screen_processor = sp.StaticImageProcessor(self.screen_capturer)
        self.terrain_analyzer = ta.PathAnalyzer()
        self.keyhandler = km.KeyboardInputManager()
        self.player_manager = pc.PlayerController(self.keyhandler, self.screen_processor, keymap, mode="teleport")

        # Platforms
        self.last_platform_hash = None
        self.current_platform_hash = None
        self.goal_platform_hash = None
        self.platform_error = 3  # If y value is same as a platform and within 3 pixels of platform border, consider to be on said platform

        # Rune
        # self.rune_model_path = rune_model_dir
        # self.rune_solver = rs.RuneDetector(self.rune_model_path, screen_capturer=self.screen_capturer, key_mgr=self.keyhandler)
        self.rune_platform_offset = 2

        # Loop Tracker
        self.loop_count = 0  # How many loops did we loop over?
        self.reset_navmap_loop_count = 10  # every x times reset navigation map, scrambling pathing
        self.navmap_reset_type = 1  # navigation map reset type. 1 for random, -1 for just reset. GETS ALTERNATED
        self.platform_fail_loops = 0  # How many loops passed and we are not on a platform?
        self.platform_fail_loop_threshold = 10  # If self.platform_fail_loops is greater than threshold, run unstick()
        self.unstick_attempts = 0  # If not on platform, how many times did we attempt unstick()?
        self.unstick_attempts_threshold = 5  # If unstick after this amount fails to get us on a known platform, abort abort.

        # Navigation

        # This sets random.randint(1, walk_probability) to decide of moonlight slash should just walk instead of glide
        # Probability of walking is (1/walk_probability) * 100
        self.walk_probability = 5

        self.restrict_moonlight_slash_probability = 5

        self.logger.debug("%s Initialization completed." % self.__class__.__name__)

    def load_and_process_platform_map(self, path="mapdata.platform"):
        retval = self.terrain_analyzer.load(path)
        self.terrain_analyzer.generate_solution_dict()
        if retval != 0:
            self.logger.debug("Loaded platform data %s" % (path))
        else:
            self.logger.debug("Failed to load platform data %s, terrain_analyzer.load returned 0" % (path))
        return retval

    def distance(self, x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def find_current_platform(self):
        current_platform_hash = None

        for key, platform in self.terrain_analyzer.oneway_platforms.items():
            if self.player_manager.y >= min(platform.start_y, platform.end_y) and \
                    self.player_manager.y <= max(platform.start_y, platform.end_y) and \
                    self.player_manager.x >= platform.start_x and \
                    self.player_manager.x <= platform.end_x:
                current_platform_hash = platform.hash
                break

        for key, platform in self.terrain_analyzer.platforms.items():
            if self.player_manager.y == platform.start_y and \
                    self.player_manager.x >= platform.start_x and \
                    self.player_manager.x <= platform.end_x:
                current_platform_hash = platform.hash
                break

        #  Add additional check to take into account imperfect platform coordinates
        for key, platform in self.terrain_analyzer.platforms.items():
            if self.player_manager.y == platform.start_y and \
                    self.player_manager.x >= platform.start_x - self.platform_error and \
                    self.player_manager.x <= platform.end_x + self.platform_error:
                current_platform_hash = platform.hash
                break

        if current_platform_hash:
            return current_platform_hash
        else:
            return 0

    def find_rune_platform(self):
        """
        Checks if a rune exists on a platform and if exists, returns platform hash
        :return: Platform hash, rune_coord_tuple of platform where the rune is located, else 0, 0 if rune does not exist
        """
        self.player_manager.update()
        rune_coords = self.screen_processor.find_rune_marker()

        if rune_coords:
            rune_platform_hash = None
            for key, platform in self.terrain_analyzer.platforms.items():
                if rune_coords[1] >= platform.start_y - self.rune_platform_offset and \
                        rune_coords[1] <= platform.start_y + self.rune_platform_offset and \
                        rune_coords[0] >= platform.start_x and \
                        rune_coords[0] <= platform.end_x:
                    rune_platform_hash = key
            for key, platform in self.terrain_analyzer.oneway_platforms.items():
                if rune_coords[1] >= platform.start_y - self.rune_platform_offset and \
                        rune_coords[1] <= platform.start_y + self.rune_platform_offset and \
                        rune_coords[0] >= platform.start_x and \
                        rune_coords[0] <= platform.end_x:
                    rune_platform_hash = key

            if rune_platform_hash:
                return rune_platform_hash, rune_coords
            else:
                return 0, 0
        else:
            return 0, 0

    def navigate_to_rune_platform(self):
        """
        Automatically goes to rune_coords by calling find_rune_platform. Update platform information before calling.
        :return: 0
        """
        rune_platform_hash, rune_coords = self.find_rune_platform()

        if not rune_platform_hash:
            return 0
        if self.current_platform_hash != rune_platform_hash:
            rune_solutions = self.terrain_analyzer.pathfind(self.current_platform_hash, rune_platform_hash)

            if rune_solutions:
                self.logger.debug("paths to rune: %s" % (" ".join(x.method for x in rune_solutions)))
                for solution in rune_solutions:
                    if self.player_manager.x < solution.lower_bound[0]:
                        # We are left of solution bounds.
                        self.player_manager.optimized_horizontal_move(solution.lower_bound[0] - 10)
                    else:
                        # We are right of solution bounds
                        self.player_manager.optimized_horizontal_move(solution.upper_bound[0] + 10)
                    time.sleep(1)

                    rune_movement_type = solution.method
                    print(rune_movement_type)
                    if rune_movement_type == ta.METHOD_DROP:
                        self.player_manager.drop()
                        time.sleep(1)
                    elif rune_movement_type == ta.METHOD_JUMPL:
                        self.player_manager.jumpl_double()
                        time.sleep(0.5)
                    elif rune_movement_type == ta.METHOD_JUMPR:
                        self.player_manager.jumpr_double()
                        time.sleep(0.5)
                    elif rune_movement_type == ta.METHOD_DBLJMP_MAX:
                        self.player_manager.dbljump_max()
                        time.sleep(1)
                    elif rune_movement_type == ta.METHOD_DBLJMP_HALF:
                        self.player_manager.dbljump_half()
                        time.sleep(1)
                    elif rune_movement_type == ta.METHOD_TELEPORTU:
                        self.player_manager.teleport_up()
                time.sleep(0.5)
            else:
                self.logger.debug("could not generate path to rune platform %s from starting platform %s" % (
                rune_platform_hash, self.current_platform_hash))
        return 0

    def unstick(self):
        """
        Run when script can't find which platform we are at.
        Solution: try random stuff to attempt it to reposition it self
        :return: None
        """
        # Method one: get off ladder
        self.player_manager.jumpr()
        time.sleep(2)
        if self.find_current_platform():
            return 0
        self.player_manager.dbljump_max()
        time.sleep(2)
        if self.find_current_platform():
            return 0

    def abort(self):
        self.keyhandler.reset()
        self.logger.debug("aborted")
        if self.log_queue:
            self.log_queue.put(["stopped", None])

    def loop(self):
        if not self.screen_capturer.ms_get_screen_hwnd():
            self.logger.debug("Failed to get MS screen rect")
            self.abort()
            return -1

        # Update Screen
        self.screen_processor.update_image(set_focus=True)

        # Update Player Coordinate
        player_minimap_pos = self.screen_processor.find_player_minimap_marker()
        if not player_minimap_pos:
            return -1
        self.player_manager.update(player_minimap_pos[0], player_minimap_pos[1])

        # User platform update
        self.current_platform_hash = None
        self.current_platform_hash = self.find_current_platform()
        # Update navigation dictionary with last_platform and current_platform
        # if self.goal_platform_hash and self.current_platform_hash == self.goal_platform_hash:
        #     self.terrain_analyzer.move_platform(self.last_platform_hash, self.current_platform_hash)

        # for i in self.terrain_analyzer.platforms.items():
        #     for k in i[1].solutions:
        #         print(k)
        #     print('new')
        # Rune Detector
        self.player_manager.update()
        rune_platform_hash, rune_coords = self.find_rune_platform()
        # print(rune_platform_hash, rune_coords)

        dest_platform_hash = random.choice(
            [key for key in self.terrain_analyzer.platforms.keys() if key != self.current_platform_hash])
        dest_platform = self.terrain_analyzer.platforms[dest_platform_hash]
        self.player_manager.update()
        random_platform_coord = (random.randint(dest_platform.start_x, dest_platform.end_x), dest_platform.start_y)

        # print(dest_platform, random_platform_coord)
        # Once we have selected the platform to move, we can generate a path using A*
        pathlist = self.terrain_analyzer.astar_pathfind((self.player_manager.x, self.player_manager.y),
                                                        goal_coords=(70, 16))
        # print(self.distance(self.player_manager.x, self.player_manager.y, 70, 16))
        # print('start c:', self.player_manager.x, self.player_manager.y)
        # print(pathlist)
        # self.terrain_analyzer.get_platform_relations()
        # (self.terrain_analyzer.platforms)

        # if rune_platform_hash:
        #     self.logger.debug("Rune found at:".format(rune_platform_hash))
        #     rune_solve_time_offset = (time.time() - self.player_manager.last_rune_solve_time)
        #
        #     if rune_solve_time_offset >= self.player_manager.rune_cooldown or rune_solve_time_offset <= 30:
        #         self.navigate_to_rune_platform()
        #         time.sleep(1)
                # self.rune_solver.press_space()
                # time.sleep(1.5)
                # solve_result = self.rune_solver.solve_auto()
                # self.logger.debug("rune_solver.solve_auto results: %d" % (solve_result))
                # if solve_result == -1:
                #     self.logger.debug("rune_solver.solve_auto failed to solve")
                #     for x in range(4):
                #         self.keyhandler.single_press(dc.DIK_LEFT)
                #
                # self.player_manager.last_rune_solve_time = time.time()
                # self.current_platform_hash = rune_platform_hash
                # time.sleep(0.5)
        # End Rune Detector