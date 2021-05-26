from directinput_constants import \
    DIK_RIGHT, \
    DIK_DOWN, \
    DIK_LEFT, \
    DIK_UP, \
    DIK_A, \
    DIK_B, \
    DIK_C, \
    DIK_D, \
    DIK_E, \
    DIK_F, \
    DIK_G, \
    DIK_H, \
    DIK_I, \
    DIK_J, \
    DIK_K, \
    DIK_L, \
    DIK_M, \
    DIK_N, \
    DIK_O, \
    DIK_P, \
    DIK_Q, \
    DIK_R, \
    DIK_S, \
    DIK_T, \
    DIK_U, \
    DIK_V, \
    DIK_W, \
    DIK_X, \
    DIK_Y, \
    DIK_Z, \
    DIK_1, \
    DIK_2, \
    DIK_3, \
    DIK_4, \
    DIK_5, \
    DIK_6, \
    DIK_7, \
    DIK_8, \
    DIK_9, \
    DIK_0, \
    DIK_ALT, \
    DIK_LCTRL, \
    DIK_SPACE, \
    DIK_COMMA, \
    DIK_PGDOWN, \
    DIK_PGUP, \
    DIK_F8, \
    DIK_F9, \
    DIK_F10, \
    DIK_F11, \
    DIK_F12, \
    DIK_SEMICOLON, \
    DIK_DASH, \
    DIK_END
from keystate_manager import DEFAULT_KEY_MAP
import time, math, random


# simple jump vertical distance: about 6 pixels

class PlayerController:
    """
    This class keeps track of character location and manages advanced movement and attacks.
    """

    def __init__(self, key_mgr, screen_handler, keymap=DEFAULT_KEY_MAP):
        """
        Class Variables:

        self.x: Known player minimap x coord. Needs to be updated manually
        self.x: Known player minimap y coord. Needs tobe updated manually
        self.key_mgr: handle to KeyboardInputManager
        self.screen_processor: handle to StaticImageProcessor
        self.goal_x: If moving, destination x coord
        self.goal_y: If moving, destination y coord
        self.busy: True if current class is calling blocking calls or in a loop
        :param key_mgr: Handle to KeyboardInputManager
        :param screen_handler: Handle to StaticImageProcessor. Only used to call find_player_minimap_marker

        Bot States:
        Idle
        ChangePlatform
        AttackinPlatform
        """
        self.x = None
        self.y = None

        self.keymap = {}
        for key, value in keymap.items():
            self.keymap[key] = value[0]
        self.jump_key = self.keymap["jump"]
        self.key_mgr = key_mgr
        self.screen_processor = screen_handler
        self.goal_x = None
        self.goal_y = None

        self.busy = False

        self.finemode_limit = 4
        self.horizontal_goal_offset = 5

        self.demonstrike_min_distance = 18

        self.horizontal_jump_distance = 10
        self.horizontal_jump_height = 9

        self.x_movement_enforce_rate = 15  # refer to optimized_horizontal_move

        self.moonlight_slash_x_radius = 13  # exceed: moonlight slash's estimalte x hitbox RADIUS in minimap coords.
        self.moonlight_slash_delay = 0.9  # delay after using MS where character is not movable

        self.horizontal_movement_threshold = 21  # Glide instead of walk if distance greater than threshold

        self.skill_cast_counter = 0
        self.skill_counter_time = 0

        self.last_shield_chase_time = 0
        self.shield_chase_cooldown = 6
        self.shield_chase_delay = 1.0  # delay after using SC where character is not movable
        self.last_shield_chase_coords = None
        self.min_shield_chase_distance = 20

        self.last_thousand_sword_time = 0
        self.thousand_sword_cooldown = 8 + 2
        self.thousand_sword_delay = 1.6 - 0.2  # delay after using thousand sword where character is not movable
        self.last_thousand_sword_coords = None
        self.min_thousand_sword_distance = 25

        self.rune_cooldown = 60 * 15  # 15 minutes for rune cooldown
        self.last_rune_solve_time = 0

        self.holy_symbol_cooldown = 60 * 3 + 1
        self.last_holy_symbol_time = 0
        self.holy_symbol_delay = 1.7

        self.hyper_body_cooldown = 60 * 3 + 1
        self.last_hyper_body_time = 0
        self.hyper_body_delay = 1.7

        self.overload_stack = 0

        self.pressing_arrow_key = False

    def update(self, player_coords_x=None, player_coords_y=None):
        """
        Updates self.x, self.y to input coordinates
        :param player_coords_x: Coordinates to update self.x
        :param player_coords_y: Coordinates to update self.y
        :return: None
        """
        if not player_coords_x:
            self.screen_processor.update_image()
            scrp_ret_val = self.screen_processor.find_player_minimap_marker()
            if scrp_ret_val:
                player_coords_x, player_coords_y = scrp_ret_val
            else:
                # raise Exception("screen_processor did not return coordinates!!")
                player_coords_x = self.x
                player_coords_y = self.y
        self.x, self.y = player_coords_x, player_coords_y

    def jump_double_curve(self, start_x, start_y, current_x):
        """
        Calculates the height at horizontal double jump starting from(start_x, start_y) at x coord current_x
        :param start_x: start x coord
        :param start_y: start y coord
        :param current_x: x of coordinate to calculate height
        :return: height at current_x
        """
        slope = 0.05
        x_jump_range = 10
        y_jump_height = 1.4
        max_coord_x = (start_x * 2 + x_jump_range) / 2
        max_coord_y = start_y - y_jump_height
        if max_coord_y <= 0:
            return 0

        y = slope * (current_x - max_coord_x) ** 2 + max_coord_y
        return max(0, y)

    def distance(self, coord1, coord2):
        return math.sqrt((coord1[0] - coord2[0]) ** 2 + (coord1[1] - coord2[1]) ** 2)

    def moonlight_slash_sweep_move(self, goal_x, glide=True, no_attack_distance=0):
        """
        This function will, while moving towards goal_x, constantly use exceed: moonlight slash and not overlapping
        This function currently does not have an time enforce implementation, meaning it may fall into an infinite loop
        if player coordinates are not read correctly.
        X coordinate max error on flat surface: +- 5 pixels
        :param goal_x: minimap x goal coordinate.
        :param glide: If True, will used optimized_horizontal_move. Else, will use horizontal_move_goal
        :param no_attack_distance: Distance in x pixels where any attack skill would not be used and just move
        :return: None
        """
        start_x = self.x
        loc_delta = self.x - goal_x
        abs_loc_delta = abs(loc_delta)

        if not no_attack_distance:
            self.moonlight_slash()
            time.sleep(abs(self.random_duration()))
        if loc_delta > 0:
            # left movement
            if no_attack_distance and no_attack_distance < abs_loc_delta:
                self.optimized_horizontal_move(self.x - no_attack_distance + self.horizontal_goal_offset)

            self.update()
            loc_delta = self.x - goal_x
            abs_loc_delta = abs(loc_delta)
            if abs_loc_delta < self.moonlight_slash_x_radius:
                self.horizontal_move_goal(goal_x)

            else:
                while True:
                    self.update()

                    if self.x <= goal_x + self.horizontal_goal_offset:
                        break

                    elif abs(self.x - goal_x) < self.moonlight_slash_x_radius * 2:
                        #  Movement distance is too short to effectively glide. So just wak
                        if glide:
                            self.optimized_horizontal_move(goal_x)
                        else:
                            self.horizontal_move_goal(goal_x)

                        if abs(self.x - start_x) >= no_attack_distance:
                            time.sleep(abs(self.random_duration()))
                            self.moonlight_slash()
                            # time.sleep(abs(self.random_duration()))
                            self.randomize_skill()


                    else:
                        if glide:
                            self.optimized_horizontal_move(
                                self.x - self.moonlight_slash_x_radius * 2 + self.random_duration(2, 0))
                        else:
                            self.horizontal_move_goal(
                                self.x - self.moonlight_slash_x_radius * 2 + self.random_duration(2, 0))

                        time.sleep(abs(self.random_duration()))
                        self.moonlight_slash()
                        # time.sleep(abs(self.random_duration()))
                        self.randomize_skill()

                    time.sleep(abs(self.random_duration()))

        elif loc_delta < 0:
            # right movement
            if no_attack_distance and no_attack_distance < abs_loc_delta:
                self.optimized_horizontal_move(self.x + no_attack_distance - self.horizontal_goal_offset)
            self.update()
            loc_delta = self.x - goal_x
            abs_loc_delta = abs(loc_delta)
            if abs_loc_delta < self.moonlight_slash_x_radius:
                self.horizontal_move_goal(goal_x)

            else:
                while Toe:
                    self.update()

                    if self.x >= goal_x - self.horizontal_goal_offset:
                        break

                    elif abs(goal_x - self.x) < self.moonlight_slash_x_radius * 2:
                        if glide:
                            self.optimized_horizontal_move(goal_x)
                        else:
                            self.horizontal_move_goal(goal_x)

                        if abs(self.x - start_x) >= no_attack_distance:
                            time.sleep(abs(self.random_duration()))
                            self.moonlight_slash()
                            # time.sleep(abs(self.random_duration()))
                            self.randomize_skill()

                    else:
                        if glide:
                            self.optimized_horizontal_move(
                                self.x + self.moonlight_slash_x_radius * 2 - abs(self.random_duration(2, 0)))
                        else:
                            self.horizontal_move_goal(
                                self.x + self.moonlight_slash_x_radius * 2 - abs(self.random_duration(2, 0)))

                        time.sleep(abs(self.random_duration()))
                        self.moonlight_slash()
                        # time.sleep(abs(self.random_duration()))
                        self.randomize_skill()

                    time.sleep(abs(self.random_duration()))

    def optimized_horizontal_move(self, goal_x, ledge=False, enforce_time=True):
        """
        Move from self.x to goal_x in as little time as possible. Uses multiple movement solutions for efficient paths. Blocking call
        :param goal_x: x coordinate to move to. This function only takes into account x coordinate movements.
        :param ledge: If true, goal_x is an end of a platform, and additional movement solutions can be used. If not, precise movement is required.
        :param enforce_time: If true, the function will stop moving after a time threshold is met and still haven't
        met the goal. Default threshold is 15 minimap pixels per second.
        :return: None
        """
        loc_delta = self.x - goal_x
        abs_loc_delta = abs(loc_delta)
        start_time = time.time()
        horizontal_goal_offset = self.horizontal_goal_offset
        if loc_delta < 0:
            # we need to move right
            time_limit = math.ceil(abs_loc_delta / self.x_movement_enforce_rate)
            if abs_loc_delta <= self.horizontal_movement_threshold:
                # Just walk if distance is less than threshold
                self.key_mgr._direct_press(DIK_RIGHT)

                # Below: use a loop to continously press right until goal is reached or time is up
                while True:
                    if time.time() - start_time > time_limit:
                        break

                    self.update()
                    # Problem with synchonizing player_pos with self.x and self.y. Needs to get resolved.
                    # Current solution: Just call self.update() (not good for redundancy)
                    if self.x >= goal_x - self.horizontal_goal_offset:
                        # Reached or exceeded destination x coordinates
                        break

                self.key_mgr._direct_release(DIK_RIGHT)

            else:
                # Distance is quite big, so we glide
                self.key_mgr._direct_press(DIK_RIGHT)
                time.sleep(abs(0.05 + self.random_duration(gen_range=0.1)))
                self.key_mgr._direct_press(self.jump_key)
                time.sleep(abs(0.15 + self.random_duration(gen_range=0.15)))
                self.key_mgr._direct_release(self.jump_key)
                time.sleep(abs(0.1 + self.random_duration(gen_range=0.15)))
                self.key_mgr._direct_press(self.jump_key)
                while True:
                    if time.time() - start_time > time_limit:
                        break

                    self.update()
                    if self.x >= goal_x - self.horizontal_goal_offset * 3:
                        break
                self.key_mgr._direct_release(self.jump_key)
                time.sleep(0.1 + self.random_duration())
                self.key_mgr._direct_release(DIK_RIGHT)


        elif loc_delta > 0:
            # we are moving to the left
            time_limit = math.ceil(abs_loc_delta / self.x_movement_enforce_rate)
            if abs_loc_delta <= self.horizontal_movement_threshold:
                # Just walk if distance is less than 10
                self.key_mgr._direct_press(DIK_LEFT)

                # Below: use a loop to continously press left until goal is reached or time is up
                while True:
                    if time.time() - start_time > time_limit:
                        break

                    self.update()
                    # Problem with synchonizing player_pos with self.x and self.y. Needs to get resolved.
                    # Current solution: Just call self.update() (not good for redundancy)
                    if self.x <= goal_x + self.horizontal_goal_offset:
                        # Reached or exceeded destination x coordinates
                        break

                self.key_mgr._direct_release(DIK_LEFT)

            else:
                # Distance is quite big, so we glide
                self.key_mgr._direct_press(DIK_LEFT)
                time.sleep(abs(0.05 + self.random_duration(gen_range=0.1)))
                self.key_mgr._direct_press(self.jump_key)
                time.sleep(abs(0.15 + self.random_duration(gen_range=0.15)))
                self.key_mgr._direct_release(self.jump_key)
                time.sleep(abs(0.1 + self.random_duration(gen_range=0.15)))
                self.key_mgr._direct_press(self.jump_key)
                while True:
                    if time.time() - start_time > time_limit:
                        break

                    self.update()
                    if self.x <= goal_x + self.horizontal_goal_offset * 3:
                        break
                self.key_mgr._direct_release(self.jump_key)
                time.sleep(0.1 + self.random_duration())
                self.key_mgr._direct_release(DIK_LEFT)

    def horizontal_move_goal(self, goal_x):
        """
        Blocking call to move from current x position(self.x) to goal_x. Only counts x coordinates.
        Refactor notes: This function references self.screen_processor
        :param goal_x: goal x coordinates
        :return: None
        """
        current_x = self.x
        if goal_x - current_x > 0:
            # need to go right:
            mode = "r"
        elif goal_x - current_x < 0:
            # need to go left:
            mode = "l"
        else:
            return 0

        if mode == "r":
            # need to go right:
            self.key_mgr._direct_press(DIK_RIGHT)
        elif mode == "l":
            # need to go left:
            self.key_mgr._direct_press(DIK_LEFT)
        while True:
            self.update()
            if not self.x:
                assert 1 == 0, "horizontal_move goal: failed to recognize coordinates"

            if mode == "r":
                if self.x >= goal_x - self.horizontal_goal_offset:
                    self.key_mgr._direct_release(DIK_RIGHT)
                    break
            elif mode == "l":
                if self.x <= goal_x + self.horizontal_goal_offset:
                    self.key_mgr._direct_release(DIK_LEFT)
                    break

    def release_keys(self):
        self.key_mgr.reset()

    def castSkill(self, key, delay, sleep_first= False):
        if sleep_first:
            time.sleep(delay)
        self.key_mgr._direct_press(self.getKey(key))
        time.sleep(delay)
        self.key_mgr._direct_release(self.getKey(key))

    def castKishin(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_F)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_F)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_F)

    def castHaku(self):
        self.key_mgr._direct_press(DIK_COMMA)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_COMMA)

    def castBoosterMw(self):
        self.key_mgr._direct_press(DIK_ALT)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_ALT)
        time.sleep(1)

    def castSpiritStone(self):
        self.key_mgr._direct_press(DIK_H)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_H)

    def castBigBoss(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_L)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_L)
        time.sleep(0.2)

    def castYoungYasha(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_G)
        time.sleep(0.05)
        self.key_mgr._direct_release(DIK_G)

    def castYuki(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_5)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_5)

    def castHs(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_Y)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_Y)

    def castSi(self):
        time.sleep(1)
        self.key_mgr._direct_press(DIK_U)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_5)

    def feedPet(self):
        self.key_mgr._direct_press(DIK_LCTRL)
        time.sleep(0.2)
        self.key_mgr._direct_press(DIK_LCTRL)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_LCTRL)

    #===Advance movement===============================
    def a_walk(self, direction):
        if self.pressing_arrow_key:
            if direction == 'left':
                print('left')
                self.key_mgr._direct_press(DIK_LEFT)
                self.key_mgr._direct_release(DIK_RIGHT)
            else:
                print('right')
                self.key_mgr._direct_press(DIK_RIGHT)
                self.key_mgr._direct_release(DIK_LEFT)
        else:
            print(direction)
            self.key_mgr._direct_press(self.getKey(direction))

        self.pressing_arrow_key = True
        self.key_mgr._direct_press(self.getKey(direction))

    def a_attack(self, key):
        self.key_mgr._direct_press(self.getKey(key))
        time.sleep(self.rand_dec(140, 240))

    def a_tele_attack(self, key):
        attack_counts = random.randint(1, 2)
        teleport_counts = random.randint(1, 2)

        for x in range(teleport_counts):
            self.key_mgr._direct_press(DIK_D)
            time.sleep(self.rand_dec(2, 3))


        for x in range(attack_counts):
            self.key_mgr._direct_press(self.getKey(key))
            time.sleep(self.rand_dec(2, 3))

    def a_telecast(self):
        glide_count = random.randint(1, 1)
        attack_counts = random.randint(1, 3)
        teleport_counts = random.randint(1, 3)

        for x in range(glide_count):
            self.key_mgr._direct_press(DIK_G)
            time.sleep(self.rand_dec(1, 2))
            # if x == range(glide_count)[-1]:
            #     time.sleep(self.rand_dec(2, 5))
            #
            # else:
            #     time.sleep(self.rand_dec(7, 14))


        for x in range(attack_counts):
            self.key_mgr._direct_press(DIK_X)
            time.sleep(self.rand_dec(2, 5))

        for x in range(teleport_counts):
            self.key_mgr._direct_press(DIK_D)

            time.sleep(self.rand_dec(2, 4))

    #==================================
    def walk(self, direction):
        self.pressing_arrow_key = True
        self.key_mgr._direct_press(self.getKey(direction))

    def tele_attack(self):
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.1)

        self.key_mgr._direct_release(DIK_X)
        self.key_mgr._direct_release(DIK_D)

    def hold_attack(self, key):
        self.key_mgr._direct_press(self.getKey(key))

    def attack(self, key):
        self.key_mgr._direct_press(self.getKey(key))
        time.sleep(0.05)
    # ==================================
    def telecast(self):
        self.key_mgr._direct_press(DIK_G)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_press(DIK_X)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_press(DIK_D)
        time.sleep(abs(0.1 + self.random_duration(0.1)))
        self.key_mgr._direct_press(DIK_X)
        time.sleep(abs(0.05 + self.random_duration(0.1)))

        # self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(DIK_G)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_X)

    def walkl(self):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(abs(0.21 + self.random_duration(0.1)))
        self.key_mgr._direct_release(DIK_LEFT)

    def walkjl(self):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.5)
        self.key_mgr._direct_press(DIK_SPACE)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_release(DIK_SPACE)

    def telel(self):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.5)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_release(DIK_D)

    def telejl(self):
        # self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(abs(0.5 + self.random_duration(0.1)))
        self.key_mgr._direct_press(DIK_D)
        time.sleep(abs(0.2 + self.random_duration(0.1)))
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(abs(0.1 + self.random_duration(0.1)))
        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_D)

    def telecastl(self):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_G)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.05)

        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_release(DIK_G)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_X)

    def backflip_attackl(self, key):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.2)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.3)
        self.key_mgr._direct_release(DIK_LEFT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_press(self.getKey(key))
        time.sleep(0.1)
        self.key_mgr._direct_release(self.getKey(key))
        self.key_mgr._direct_release(self.jump_key)

    def walkr(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.21)
        self.key_mgr._direct_release(DIK_RIGHT)

    def walkjr(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.5)
        self.key_mgr._direct_press(DIK_SPACE)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(DIK_SPACE)

    def teler(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.5)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.2)
        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(DIK_D)

    def telejr(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.5)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.2)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_D)

    def telecastr(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_G)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.05)

        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(DIK_G)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_X)

    def backflip_attackr(self, key):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.2)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.3)
        self.key_mgr._direct_release(DIK_RIGHT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_press(self.getKey(key))
        time.sleep(0.1)
        self.key_mgr._direct_release(self.getKey(key))
        self.key_mgr._direct_release(self.jump_key)


    def teleu(self):
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_UP)
        self.key_mgr._direct_release(DIK_D)

    def teleju(self):
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.30)
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_UP)
        self.key_mgr._direct_release(DIK_D)

    def teled(self):
        self.key_mgr._direct_press(DIK_DOWN)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_DOWN)

    def telejd(self):
        self.key_mgr._direct_press(DIK_DOWN)
        time.sleep(0.05)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.35)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_DOWN)
    def telel_attack(self):
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_X)
        time.sleep(0.1)

        self.key_mgr._direct_release(DIK_X)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_LEFT)

    def telejl_attack(self):
        # self.key_mgr._direct_press(DIK_LEFT)
        # time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1)

        # flip_right_attack_chance = random.randint(0, 100)
        #
        # if flip_right_attack_chance <= 20:
        #     print('Casting chance attack (attack opposite direction)')
        #     self.key_mgr._direct_release(DIK_LEFT)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_press(DIK_RIGHT)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_press(DIK_X)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_release(DIK_RIGHT)
        #     self.key_mgr._direct_press(DIK_LEFT)
        #     self.pressing_arrow_key = False

        self.key_mgr._direct_press(DIK_X)
        self.key_mgr._direct_release(DIK_X)
        self.key_mgr._direct_release(self.jump_key)
        # self.key_mgr._direct_release(DIK_LEFT)

    def teler_attack(self):
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_X)
        self.key_mgr._direct_release(DIK_X)
        self.key_mgr._direct_release(DIK_D)
        self.key_mgr._direct_release(DIK_RIGHT)

    def telejr_attack(self):
        # self.key_mgr._direct_press(DIK_RIGHT)
        # time.sleep(0.05)
        self.key_mgr._direct_press(DIK_D)
        time.sleep(abs(0.1 + self.random_duration(0.1)))
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(abs(0.1 + self.random_duration(0.1)))

        # flip_right_attack_chance = random.randint(0, 100)
        #
        # if flip_right_attack_chance <= 20:
        #     print('Casting chance attack (attack opposite direction)')
        #     self.key_mgr._direct_release(DIK_RIGHT)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_press(DIK_LEFT)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_press(DIK_X)
        #     time.sleep(0.1)
        #     self.key_mgr._direct_release(DIK_LEFT)
        #     self.key_mgr._direct_press(DIK_RIGHT)
            # self.pressing_arrow_key = False

        self.key_mgr._direct_press(DIK_X)
        self.key_mgr._direct_release(DIK_X)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_LEFT)

    def j_attack(self):
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1 + self.random_duration(0.05))
        self.key_mgr._direct_press(DIK_C)
        time.sleep(0.1 + self.random_duration(0.05))

        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_C)

    def dj_attack(self):
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1 + self.random_duration(0.05))
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(abs(0.1 + self.random_duration(0.05)))
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(abs(0.05 + self.random_duration(0.05)))

        attack_counts = random.randint(2, 4)

        for x in range(attack_counts):
            self.key_mgr._direct_press(DIK_C)
            time.sleep(0.1 + self.random_duration(0.05))
            self.key_mgr._direct_release(DIK_C)
            time.sleep(0.05 + self.random_duration(0.05))

        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_C)

    def spawn_altar(self):
        self.key_mgr._direct_press(DIK_DOWN)
        time.sleep(self.rand_dec(20, 50))
        self.key_mgr._direct_press(DIK_C)
        time.sleep(self.rand_dec(20, 50))

    def dbljump_max(self):
        """Warining: is a blocking call"""
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1 + self.random_duration(0.05))
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(abs(0.05 + self.random_duration(0.05)))
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(abs(0.01 + self.random_duration(0.05)))
        self.key_mgr._direct_release(DIK_UP)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(abs(0.01 + self.random_duration(0.05)))
        self.key_mgr._direct_release(DIK_UP)

    def dbljump_half(self):
        """Warining: is a blocking call"""
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1 + self.random_duration(0.1))
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(0.23 + self.random_duration(0.1))
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(0.01)
        self.key_mgr._direct_release(DIK_UP)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_UP)
        time.sleep(abs(0.01 + self.random_duration(0.15)))
        self.key_mgr._direct_release(DIK_UP)

    def dbljump_timed(self, delay):
        """
        If using linear eq, delay explicit amount of time for double jump
        :param delay: time before double jump command is issued in float seconds
        :return: None
        """
        self.key_mgr.single_press(self.jump_key)
        time.sleep(delay)
        self.key_mgr.single_press(DIK_UP)
        time.sleep(0.01)
        self.key_mgr.single_press(DIK_UP)

    def jumpl(self):
        """Blocking call"""
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.05)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_LEFT)
        self.key_mgr._direct_release(self.jump_key)

    def jumpl_double(self):
        """Blocking call"""
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_release(DIK_LEFT)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(abs(0.05 + self.random_duration(0.2)))
        self.key_mgr._direct_release(DIK_LEFT)

    def jumpl_glide(self):
        """Blocking call"""
        self.key_mgr._direct_press(DIK_LEFT)
        time.sleep(0.05)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.15)
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.2)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_LEFT)

    def jumpr(self):
        """Blocking call"""
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.05)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_RIGHT)
        self.key_mgr._direct_release(self.jump_key)

    def jumpr_double(self):
        """Blocking call"""
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(abs(0.05 + self.random_duration(0.1)))
        self.key_mgr._direct_release(DIK_RIGHT)
        time.sleep(0.05)
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(abs(0.05 + self.random_duration(0.2)))
        self.key_mgr._direct_release(DIK_RIGHT)

    def jumpr_glide(self):
        """Blocking call"""
        self.key_mgr._direct_press(DIK_RIGHT)
        time.sleep(0.05)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.15)
        self.key_mgr._direct_release(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.2)
        self.key_mgr._direct_release(self.jump_key)
        self.key_mgr._direct_release(DIK_RIGHT)

    def drop(self):
        """Blocking call"""
        self.key_mgr._direct_press(DIK_DOWN)
        time.sleep(0.1)
        self.key_mgr._direct_press(self.jump_key)
        time.sleep(0.1)
        self.key_mgr._direct_release(DIK_DOWN)
        time.sleep(0.1)
        self.key_mgr._direct_release(self.jump_key)

    def random_duration(self, gen_range=0.1, digits=2):
        """
        returns a random number x where -gen_range<=x<=gen_range rounded to digits number of digits under floating points
        :param gen_range: float for generating number x where -gen_range<=x<=gen_range
        :param digits: n digits under floating point to round. 0 returns integer as float type
        :return: random number float
        """
        d = round(random.uniform(0, gen_range), digits)
        if random.choice([1, -1]) == -1:
            d *= -1
        return d

    def rand_dec(self, start, end):
        r1 = start / 100
        r2 = end / 100
        rand = round(random.uniform(r1, r2), 3)

        return rand

    def getKey(self, key):
        getKey = {  # tkinter event keysym to dik key code coversion table
            "ALT_L": DIK_ALT,
            "CONTROL_L": DIK_LCTRL,
            "space": DIK_SPACE,
            "comma": DIK_COMMA,
            "pgdown": DIK_PGDOWN,
            "pgup": DIK_PGUP,
            "a": DIK_A,
            "b": DIK_B,
            "c": DIK_C,
            "d": DIK_D,
            "e": DIK_E,
            "f": DIK_F,
            "g": DIK_G,
            "h": DIK_H,
            "i": DIK_I,
            "j": DIK_J,
            "k": DIK_K,
            "l": DIK_L,
            "m": DIK_M,
            "n": DIK_N,
            "o": DIK_O,
            "p": DIK_P,
            "q": DIK_Q,
            "r": DIK_R,
            "s": DIK_S,
            "t": DIK_T,
            "u": DIK_U,
            "v": DIK_V,
            "w": DIK_W,
            "x": DIK_X,
            "y": DIK_Y,
            "z": DIK_Z,
            "1": DIK_1,
            "2": DIK_2,
            "3": DIK_3,
            "4": DIK_4,
            "5": DIK_5,
            "6": DIK_6,
            "7": DIK_7,
            "8": DIK_8,
            "9": DIK_9,
            "0": DIK_0,
            "up": DIK_UP,
            "down": DIK_DOWN,
            "left": DIK_LEFT,
            "right": DIK_RIGHT,

            "end": DIK_END,
            "-": DIK_DASH,
            "F8": DIK_F8,
            "F9": DIK_F9,
            "F10": DIK_F10,
            "F11": DIK_F11,
            "F12": DIK_F12,
            ";": DIK_SEMICOLON
        }

        return getKey[key]

