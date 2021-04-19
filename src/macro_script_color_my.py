import keystate_manager as km
import player_controller as pc
import screen_processor as sp
import terrain_analyzer as ta
import directinput_constants as dc
import rune_solver as rs
import logging, math, time, random
import randoml

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

class MacroController:
    # 3rd param rune_model_dir=r"arrow_classifier_keras_gray.h5",
    def __init__(self, keymap=km.DEFAULT_KEY_MAP, log_queue=None):

        #sys.excepthook = self.exception_hook

        self.screen_capturer = sp.MapleScreenCapturer()
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(logging.DEBUG)
        self.log_queue = log_queue
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler("logging.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        self.zero_coord_count = 0
        self.logger = CustomLogger(logger, self.log_queue)
        self.logger.debug("%s init"%self.__class__.__name__)
        self.screen_processor = sp.StaticImageProcessor(self.screen_capturer)
        self.terrain_analyzer = ta.PathAnalyzer()
        self.keyhandler = km.KeyboardInputManager()
        self.player_manager = pc.PlayerController(self.keyhandler, self.screen_processor, keymap)


        self.last_platform_hash = None
        self.current_platform_hash = None
        self.goal_platform_hash = None

        self.platform_error = 3  # If y value is same as a platform and within 3 pixels of platform border, consider to be on said platform

        # self.rune_model_path = rune_model_dir
        # self.rune_solver = rs.RuneDetector(self.rune_model_path, screen_capturer=self.screen_capturer, key_mgr=self.keyhandler)
        self.rune_platform_offset = 2

        self.loop_count = 0  # How many loops did we loop over?
        self.reset_navmap_loop_count = 10  # every x times reset navigation map, scrambling pathing
        self.navmap_reset_type = 1  # navigation map reset type. 1 for random, -1 for just reset. GETS ALTERNATED

        self.walk_probability = 5
        # This sets random.randint(1, walk_probability) to decide of moonlight slash should just walk instead of glide
        # Probability of walking is (1/walk_probability) * 100

        self.restrict_moonlight_slash_probability = 5

        self.platform_fail_loops = 0
        # How many loops passed and we are not on a platform?

        self.platform_fail_loop_threshold = 10
        # If self.platform_fail_loops is greater than threshold, run unstick()

        self.unstick_attempts = 0
        # If not on platform, how many times did we attempt unstick()?

        self.unstick_attempts_threshold = 5
        # If unstick after this amount fails to get us on a known platform, abort abort.

        self.logger.debug("%s init finished"%self.__class__.__name__)

        self.kishin_time = 0
        self.haku_time = 0
        self.booster_mw_time = 0
        self.spirit_stone_time = 0
        self.big_boss_time = 0
        self.young_yasha_time = 0
        self.yuki_time = 0
        self.hs_time = 0
        self.si_time = 0
        self.pet_feed_time = 0

        self.direction_change_time = 0

    def load_and_process_platform_map(self, path="mapdata.platform"):
        retval = self.terrain_analyzer.load(path)
        self.terrain_analyzer.generate_solution_dict()
        if retval != 0:
            self.logger.debug("Loaded platform data %s"%(path))
        else:
            self.logger.debug("Failed to load platform data %s, terrain_analyzer.load returned 0"%(path))
        return retval

    def distance(self, x1, y1, x2, y2):
        return math.sqrt((x1-x2)**2 + (y1-y2)**2)

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
                        self.player_manager.horizontal_move_goal(solution.lower_bound[0])
                    else:
                        # We are right of solution bounds
                        self.player_manager.horizontal_move_goal(solution.upper_bound[0])
                    time.sleep(1)
                    rune_movement_type = solution.method
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
                time.sleep(0.5)
            else:
                self.logger.debug("could not generate path to rune platform %s from starting platform %s"%(rune_platform_hash, self.current_platform_hash))
        return 0

    def log_skill_usage_statistics(self):
        """
        checks self.player_manager.skill_cast_time and count and logs them if time is greater than threshold
        :return: None
        """
        if not self.player_manager.skill_counter_time:
            self.player_manager.skill_counter_time = time.time()
        if time.time() - self.player_manager.skill_counter_time > 60:

            self.logger.debug("skills casted in duration %d: %d skill/s: %f"%(int(time.time() - self.player_manager.skill_counter_time), self.player_manager.skill_cast_counter, self.player_manager.skill_cast_counter/int(time.time() - self.player_manager.skill_counter_time)))
            self.player_manager.skill_cast_counter = 0
            self.player_manager.skill_counter_time = time.time()

    def loop(self):
        # self.player_manager.teled()
        # Update Screen
        self.screen_processor.update_image(set_focus=True)
        # Update Constants
        player_minimap_pos = self.screen_processor.find_player_minimap_marker()

        if not player_minimap_pos:
            return -1
        self.player_manager.update(player_minimap_pos[0], player_minimap_pos[1])

        self.current_platform_hash = None
        get_current_platform = self.find_current_platform()

        # Initial Buffs
        if not self.direction_change_time:
            self.direction_change_time = time.time()

        if not self.haku_time or time.time() - self.haku_time > 300:
            print('Casting Haku buff')
            self.haku_time = time.time()
            self.player_manager.castHaku()
        if not self.kishin_time or time.time() - self.kishin_time > 120:
            print('Casting Kishin buff')
            self.kishin_time = time.time()
            self.player_manager.castKishin()
        if not self.booster_mw_time or time.time() - self.booster_mw_time > 150:
            print('Casting MW buff')
            self.booster_mw_time = time.time()
            self.player_manager.castBoosterMw()
        if not self.spirit_stone_time or time.time() - self.spirit_stone_time > 230:
            print('Casting Spirit Stone')
            self.spirit_stone_time = time.time()
            self.player_manager.castSpiritStone()
        if not self.big_boss_time or time.time() - self.big_boss_time > 190:
            print('Casting Big Boss')
            self.big_boss_time = time.time()
            self.player_manager.castBigBoss()
        if not self.young_yasha_time or time.time() - self.young_yasha_time > 33:
            print('Casting Young Yasha')
            self.young_yasha_time = time.time()
            self.player_manager.castYoungYasha()
        if not self.yuki_time or time.time() - self.yuki_time > 92:
            print('Casting Yuki')
            self.yuki_time = time.time()
            self.player_manager.castYuki()
        if not self.hs_time or time.time() - self.hs_time > 183:
            print('Casting HS')
            self.hs_time = time.time()
            self.player_manager.castHs()
        if not self.si_time or time.time() - self.si_time > 187:
            print('Casting SI')
            self.si_time = time.time()
            self.player_manager.castSi()
        if not self.pet_feed_time or time.time() - self.pet_feed_time > 148:
            print('Feeding pets')
            self.pet_feed_time = time.time()
            self.player_manager.feedPet()

        if get_current_platform == 0:
            self.zero_coord_count += 1
        else:
            self.zero_coord_count = 0
        if self.zero_coord_count > 4 and get_current_platform == 0:
            # random_movement = round(random.random())
            self.player_manager.teleu()
            # if(random_movement == 0):
            #     self.player_manager.teleu()
            # else:
            #     self.player_manager.teled()

        if get_current_platform == '764feb49':
            print('Moving up')
            self.player_manager.teleu()
        elif (get_current_platform == '9540508d') and (self.player_manager.x < 75) and not 48 <= self.player_manager.x < 55:
            print('Moving up')
            self.player_manager.teleu()
        elif (get_current_platform == '9540508d') and (self.player_manager.x >= 47):
            print('Moving left attack')
            change_direction = random.randint(1, 100)
            if 130 <= self.player_manager.x <= 170 and change_direction <= 20 and time.time() - self.direction_change_time > 16:
                print('Changing direction to attack')
                self.player_manager.teler_attack()
                change_direction = time.time()
            self.player_manager.telel_attack()
        elif get_current_platform == 'a7de5437':
            print('Moving right attack')
            change_direction = random.randint(1, 100)
            if 90 <= self.player_manager.x <= 125 and change_direction <= 20 and time.time() - self.direction_change_time > 16:
                print('Changing direction to attack')
                self.player_manager.telel_attack()
                change_direction = time.time()
            self.player_manager.teler_attack()
        elif get_current_platform == 'd275878a' and self.player_manager.x < 165:
            print('Moving right attack')
            self.player_manager.teler_attack()
        elif get_current_platform == 'd275878a' and self.player_manager.x >= 165:
            print('Moving down')
            random_movement = round(random.random())

            if (random_movement == 0):
                self.player_manager.teled()
            else:
                self.player_manager.drop()
        # self.keyhandler.single_press(dc.DIK_LCTRL, duration=2)

        # #End inter-platform movement
        #
        # # Other buffs
        # self.player_manager.holy_symbol()
        # self.player_manager.hyper_body()
        # self.player_manager.release_overload()
        # time.sleep(0.05)
        #
        # # Finished
        # self.loop_count += 1
        # return 0


    def unstick(self):
        """
        Run when script can't find which platform we are at.
        Solution: try random stuff to attempt it to reposition it self
        :return: None
        """
        #Method one: get off ladder
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

