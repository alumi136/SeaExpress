import pygame, os
#start pygame
pygame.init()
#start font on pygame
pygame.font.init()
#set display size (width, height)
screen = pygame.display.set_mode((600, 400))
#set title for this game
pygame.display.set_caption('Maze')
#wall color
teal = (0, 255, 110)
red = (255, 0, 0)
#game group
def game():
    #set the constant move functions for keydown
    playermovepos_x_add = False
    playermovepos_x_minus = False
    playermovepos_y_add = False
    playermovepos_y_minus = False
    #player positions
    player_x = 25
    player_y = 355
    #button positions
    b1_x = 85
    b1_y = 365
    b2_x = 95
    b2_y = 40
    b3_x = 308
    b3_y = 40
    #button_walls positions
    bw1_x = 535
    bw2_x = 535
    bw3_x = 535
    bw1_y = 150
    bw2_y = 190
    bw3_y = 230
    #sets the function that decides to start or end game
    game = True
    #create a clock refresh rate
    clock = pygame.time.Clock()
    #for loop(draw wall one) count
    forloop = True
    #game's loop
    while game == True:
        screen.fill((0, 0, 0))
        #wall drawing
        walls = [
        pygame.draw.rect(screen, teal, (0, 0, 20, 400)),
        pygame.draw.rect(screen, teal, (580, 0, 20, 400)),
        pygame.draw.rect(screen, teal, (0, 380, 600, 20)),
        pygame.draw.rect(screen, teal, (0, 0, 600, 20)),
        pygame.draw.rect(screen, teal, (50, 300, 20, 100)),
        pygame.draw.rect(screen, teal, (50, 280, 425, 20)),
        pygame.draw.rect(screen, teal, (515, 50, 20, 300)),
        pygame.draw.rect(screen, teal, (100, 330, 435, 20)),
        pygame.draw.rect(screen, teal, (100, 330, 20, 60)),
        pygame.draw.rect(screen, teal, (20, 230, 150, 20)),
        pygame.draw.rect(screen, teal, (210, 230, 100, 20)),
        pygame.draw.rect(screen, teal, (350, 230, 165, 20)),
        pygame.draw.rect(screen, teal, (210, 60, 20, 170)),
        pygame.draw.rect(screen, teal, (50, 180, 280, 20)),
        pygame.draw.rect(screen, teal, (50, 0, 20, 80)),
        pygame.draw.rect(screen, teal, (50, 110, 120, 20)),
        pygame.draw.rect(screen, teal, (50, 160, 20, 30)),
        pygame.draw.rect(screen, teal, (70, 60, 100, 20)),
        pygame.draw.rect(screen, teal, (105, 130, 20, 10)),
        pygame.draw.rect(screen, teal, (150, 170, 20, 10)),
        pygame.draw.rect(screen, teal, (265, 0, 20, 100)),
        pygame.draw.rect(screen, teal, (285, 80, 180, 20)),
        pygame.draw.rect(screen, teal, (225, 130, 150, 20)),
        pygame.draw.rect(screen, teal, (365, 180, 20, 50)),
        pygame.draw.rect(screen, teal, (415, 80, 20, 115)),
        pygame.draw.rect(screen, teal, (415, 175, 60, 20)),
        pygame.draw.rect(screen, teal, (475, 127, 60, 20)),
        pygame.draw.rect(screen, teal, (330, 20, 20, 25)),
        pygame.draw.rect(screen, teal, (385, 55, 20, 25)),
        pygame.draw.rect(screen, teal, (440, 20, 20, 25))
        ]
        #button draw
        b1 = pygame.draw.circle(screen, red, (b1_x, b1_y), 12)
        b2 = pygame.draw.circle(screen, red, (b2_x, b2_y), 12)
        b3 = pygame.draw.circle(screen, red, (b3_x, b3_y), 12)
        #button_wall draw
        bw1 = pygame.draw.rect(screen, red, (bw1_x, bw1_y, 45, 20))
        bw2 = pygame.draw.rect(screen, red, (bw2_x, bw2_y, 45, 20))
        bw3 = pygame.draw.rect(screen, red, (bw3_x, bw3_y, 45, 20))
        exitsquare = pygame.draw.rect(screen, (255, 170, 0), (125, 355, 20, 20))
        #detect input
        for event in pygame.event.get():
            #whether or not if the player presses the 'X' button
            if event.type == pygame.QUIT:
                game = False
            #key
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_w:
                    playermovepos_y_minus = True
                if event.key == pygame.K_a:
                    playermovepos_x_minus = True
                if event.key == pygame.K_s:
                    playermovepos_y_add = True
                if event.key == pygame.K_d:
                    playermovepos_x_add = True
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_w:
                    playermovepos_y_minus = False
                if event.key == pygame.K_a:
                    playermovepos_x_minus = False
                if event.key == pygame.K_s:
                    playermovepos_y_add = False
                if event.key == pygame.K_d:
                    playermovepos_x_add = False
        #
        old_x = player_x
        old_y = player_y
        #detect key input then move
        if playermovepos_x_add:
            player_x += 1
        if playermovepos_x_minus:
            player_x -= 1
        if playermovepos_y_add:
            player_y += 1
        if playermovepos_y_minus:
            player_y -= 1
        player = pygame.Rect(player_x, player_y, 20, 20)
        
        for wall in walls:
            if player.colliderect(wall):
                player_x = old_x
                player_y = old_y
                player = pygame.Rect(player_x, player_y, 20, 20)
                break
                
        # --- 修正區塊開始 ---
        if player.colliderect(bw1):
            player_x = old_x
            player_y = old_y
            player = pygame.Rect(player_x, player_y, 20, 20)
            
        if player.colliderect(bw2):
            player_x = old_x
            player_y = old_y
            player = pygame.Rect(player_x, player_y, 20, 20)
            
        if player.colliderect(bw3):
            player_x = old_x
            player_y = old_y
            player = pygame.Rect(player_x, player_y, 20, 20)
        # --- 修正區塊結束 ---
            
        if player.colliderect(b1):
            b1_x = 1000
            b1_y = 1000
            bw1_x = 1000
            bw1_y = 1000
        if player.colliderect(b2):
            b2_x = 1000
            b2_y = 1000
            bw2_x = 1000
            bw2_y = 1000
        if player.colliderect(b3):
            b3_x = 1000
            b3_y = 1000
            bw3_x = 1000
            bw3_y = 1000
        #draws the player with color
        pygame.draw.rect(screen, (0, 120, 255), player)        
        #updates game data to screen
        pygame.display.flip()
        #set the game's refresh rate
        clock.tick(60)
game()