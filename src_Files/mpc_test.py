# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

import matplotlib.pyplot as plt
import cvxpy as cp
import math
import numpy as np
import sys
sys.path.append("../../PathPlanning/CubicSpline/")
import cubic_spline_planner
import random
from operator import add

#set run_code=1 to run navigation through moving obstacles
#set run_code=2 to run only path following using MPC
#set run_code=3 to run only potential field
run_code=1

road = False
save_simulation = False 
path_planning = True
Nx = 4 #number of states
Nu = 2 #number of control inputs
dt=0.2
DT=0.2
W_track = 1.5 #wheel track in metre
W_base = 3.5 #wheel base in metre

N_search = 10 # search for closest point in the next N_search points on the path
H = 5 # Horizon length
simulation_time_limit = 100 #seconds
accept_dist = 0.2 #acceptable destination distance
accept_stop_v = 0.05 #acceptable stopping velocity

desired_speed = 5           # m/s
max_speed = 15              # m/s
max_reverse_speed = 5       # m/s
max_steer_angle = np.pi / 4     #max steering angle
max_steer_rate = np.pi / 6      #max steering speed
max_acc = 2                     #maximum acceleration m/s^2

W1 = np.array([0.01, 0.01])  # input weightage
W2 = np.array([2.0, 2.0, 0.5, 0.5])  # state error weightage
W3 = np.array([0.01, 0.1])  # rate of input change weightage
W4 = W2  # state error weightage

#potential field
sx = 0.0  # start x position [m]
sy = -5.0  # start y positon [m]
gx = 50.0  # goal x position [m]
gy = 30.0  # goal y position [m]
grid_size = 0.2  # potential grid size [m]
robot_radius = 5.0  # robot radius [m]
NUM_OF_OBSTACLES=12
    
################################################################################################### Class state
class State:
    def __init__(self,x_state,y_state,yaw,velocity):
        self.x = x_state
        self.y = y_state
        self.yaw = yaw
        self.v = velocity
    
    #Update state variable for given acceleration and steering angle
    def update_state(self, acc, steer_angle):
        self.x = self.x + self.v * np.cos(self.yaw) * dt
        self.y = self.y + self.v * np.sin(self.yaw) * dt
        self.yaw = self.yaw + (self.v / W_base) * np.tan (steer_angle) * dt
        self.v = self.v + acc * dt

    def state_to_vec(self):
        state_vec=np.array([self.x, self.y, self.yaw, self.v])
        return state_vec
    #end  

################################################################################################### ########################### plot_car
# Vehicle parameters
L = 4.5  # LENGTH[m]
W = 2.0  # WIDTH[m]
D = 1.0  # BACKTOWHEEL[m]
WD = 0.6  # WHEEL_DIA[m]
WW= 0.25  # WHEEL_WIDTH[m]
WB = 2.5  # [m]

def plot_car(x, y, yaw, steer=0.0, cabcolor="-y", truckcolor="-k"):  # pragma: no cover

    rotate=np.array([[np.cos(yaw),-np.sin(yaw)],[np.sin(yaw),np.cos(yaw)]])
    rotate_steer=np.array([[np.cos(steer),-np.sin(steer)],[np.sin(steer),np.cos(steer)]])
    
    car=np.array([[-D,-D,(L-D),(L-D),-D],[W/2,-W/2,-W/2,W/2,W/2]])
    car=np.matmul(rotate,car)
    car[0,:] += x
    car[1,:] += y
    plt.plot(car[0,:],car[1,:],cabcolor)
    
    wheel1=np.array([[-WD/2,-WD/2,WD/2,WD/2,-WD/2],[WW/2,-WW/2,-WW/2,WW/2,WW/2]])
    wheel2=np.array([[-WD/2,-WD/2,WD/2,WD/2,-WD/2],[WW/2,-WW/2,-WW/2,WW/2,WW/2]])
    wheel_f1=wheel1
    wheel_f2=wheel1
    wheel_f1=np.matmul(rotate_steer,wheel_f1)
    wheel_f2=np.matmul(rotate_steer,wheel_f2)
    
    wheel1[1,:] += 1.25
    wheel1=np.matmul(rotate,wheel1)
    wheel1[0,:] += x
    wheel1[1,:] += y
    plt.plot(wheel1[0,:],wheel1[1,:],truckcolor)

    wheel2
    wheel2[1,:] -= 1.25
    wheel2=np.matmul(rotate,wheel2)
    wheel2[0,:] += x
    wheel2[1,:] += y
    plt.plot(wheel2[0,:],wheel2[1,:],truckcolor)
    
    wheel_f1[0,:] += 2.5
    wheel_f1[1,:] += 1.25
    wheel_f1=np.matmul(rotate,wheel_f1)
    wheel_f1[0,:] += x
    wheel_f1[1,:] += y
    plt.plot(wheel_f1[0,:],wheel_f1[1,:],truckcolor) 
    
    wheel_f2[0,:] += 2.5
    wheel_f2[1,:] -= 1.25
    wheel_f2=np.matmul(rotate,wheel_f2)
    wheel_f2[0,:] += x
    wheel_f2[1,:] += y
    plt.plot(wheel_f2[0,:],wheel_f2[1,:],truckcolor)
    plt.plot(x, y, "*")
################################################################################################### dynamic_model
def dynamic_model(velocity, yaw, steer):
    A=np.array([[1.0 , 0.0 , - dt * velocity * math.sin(yaw), dt * math.cos(yaw) ],\
                [0.0 , 1.0 , dt * velocity * math.cos(yaw),  dt * math.sin(yaw)],\
                [0.0 , 0.0 , 1.0                , dt * math.tan(steer) / W_base],\
                [0.0 , 0.0 , 0.0 , 1.0]])

    B=np.array([[0.0 , 0.0 ],\
                [0.0 , 0.0 ],\
                [0.0 , dt * velocity / (W_base * math.cos(steer) ** 2) ],\
                [dt  , 0.0]])


    C=np.array([dt * velocity * math.sin(yaw) * yaw,\
                 - dt * velocity * math.cos(yaw) * yaw ,\
                - dt * velocity * steer / (W_base * math.cos(steer) ** 2) ,\
                0.0])
    return A, B, C

################################################################################################### calc_predicted_trajectory
def calc_predicted_trajectory(acc,steer,cur_state_vec):
    traj_pred = np.zeros((Nx,H+1))
    traj_pred[:,0]=cur_state_vec.T
    pred_state=State(cur_state_vec[0], cur_state_vec[1], cur_state_vec[2], cur_state_vec[3])
    for i in range(H):
        pred_state.update_state(acc[i], steer[i])
        temp_state=pred_state.state_to_vec()
        traj_pred[:,i+1]=temp_state.T
    return traj_pred
    
################################################################################################### run_MPC
def run_MPC(traj_des, cur_state_vec, mpc_acc, mpc_steer, steer_des, goal):

    for iter in range(3):
        traj_pred = calc_predicted_trajectory(mpc_acc,mpc_steer,cur_state_vec)
        x = cp.Variable([Nx, H+1])
        u = cp.Variable([Nu, H])

        cost = 0.0
        constraints = []
        for i in range(H):
            cost += cp.sum(W1 * cp.square(u[:, i]))                                   # input weightage
            cost += cp.sum(W2 * cp.square(traj_des[:, i] - x[:, i]))                  # state error weightage
            #cost += cp.sum(W2 * cp.square([goal[0],goal[1],0,0] - x[:, i]))                  # terminal cost
            if i < (H - 1):
                cost += cp.sum(W3 * cp.square(u[:, i+1] - u[:, i]))                    # rate of input change weightage
                constraints += [cp.abs(u[1, i+1] - u[1, i]) <= max_steer_rate * dt]
            
            A,B,C = dynamic_model(traj_pred[3,i], traj_pred[2,i], mpc_steer[i])
            constraints += [x[:, i+1] == A * x[:, i] + B * u[:, i] + C]
        
        
        cost += cp.sum(W4 * cp.square(traj_des[:, H] - x[:, H]))                      # final state error weightage
        #cost += cp.sum(10 * cp.square([goal[0],goal[1]] - x[:2, H]))                  # terminal cost
       
        constraints += [x[:, 0] == cur_state_vec]
        constraints += [x[3, :] <= max_speed]
        constraints += [x[3, :] >= -max_reverse_speed]
        constraints += [u[1, :] <= max_steer_angle]
        constraints += [u[1, :] >= -max_steer_angle]
        constraints += [u[0, :] <= max_acc]
        constraints += [u[0, :] >= -3*max_acc] 

        prob = cp.Problem(cp.Minimize(cost), constraints)
        prob.solve()

        mpc_x = x.value[0, :]
        mpc_y = x.value[1, :]
        mpc_yaw = x.value[2, :]
        mpc_v = x.value[3, :]
        mpc_acc = u.value[0, :]
        mpc_steer = u.value[1, :]
        lyap_val=0
        lap_u=0
        lap_x=0
        lap_du=0
        for i in range(H):
            lyap_val += np.sum(W1 * np.square(u.value[:, i]))                                   # input weightage
            lap_u += np.sum(W1 * np.square(u.value[:, i]))
            lyap_val += np.sum(W2 * np.square(traj_des[:, i] - x.value[:, i]))                  # state error weightage
            lap_x += np.sum(W2 * np.square(traj_des[:, i] - x.value[:, i]))
            if i < (H - 1):
                lyap_val += np.sum(W3 * np.square(u.value[:, i+1] - u.value[:, i]))                    # rate of input change weightage
                lap_du += np.sum(W3 * np.square(u.value[:, i+1] - u.value[:, i]))
        lyap_val += np.sum(W4 * np.square(traj_des[:, H] - x.value[:, H]))
        lap_x += np.sum(W4 * np.square(traj_des[:, H] - x.value[:, H]))
        #yap_val += np.sum(W2 * np.square(x.value[:, 1]))
            
        aaaa=5
    return mpc_x, mpc_y, mpc_yaw, mpc_v, mpc_acc, mpc_steer, lyap_val, lap_u, lap_x, lap_du

################################################################################################### cal_desired_trajectory (current_state, path_x, path_y,target_pt )
def cal_desired_trajectory(cur_state_vec, path_x, path_y, dist_step, path_yaw, target_pt):
    traj_des = np.zeros((Nx,H+1))
    steer_des = np.zeros((1,H+1))
    distance = 0
    total_pts = len(path_x)
    
    target_pt = get_closest_point_on_path(path_x, path_y, cur_state_vec, target_pt)

    traj_des[0,0] = path_x[target_pt]
    traj_des[1,0] = path_y[target_pt]
    traj_des[2,0] = path_yaw[target_pt]
    traj_des[3,0] = desired_speed
    
   
    for i in range(H):
        distance += abs(cur_state_vec[3]) * dt
        pts_travelled = int(round(distance/dist_step))

        if (target_pt+pts_travelled)<total_pts:
            traj_des[0,i+1] = path_x[target_pt + pts_travelled]
            traj_des[1,i+1] = path_y[target_pt + pts_travelled]
            traj_des[2,i+1] = path_yaw[target_pt + pts_travelled]
            if (target_pt+pts_travelled) == total_pts - 1:
                traj_des[3,i+1] = 0.0
            else:
                traj_des[3,i+1] = desired_speed
        else:
            traj_des[0,i+1] = path_x[-1]
            traj_des[1,i+1] = path_y[-1]
            traj_des[2,i+1] = path_yaw[-1]
            traj_des[3,i+1] = 0.0
    if traj_des[3,1] == 0.0:
        traj_des[3,0] = 0.0
    return traj_des, target_pt, steer_des   
            
################################################################################################### get_closest_point_on_path
def get_closest_point_on_path(path_x, path_y, cur_state_vec, point):
    next_x = path_x[point:point+N_search]
    next_y = path_y[point:point+N_search]
    diff_x = next_x-cur_state_vec[0]
    diff_y = next_y-cur_state_vec[1]
    dist_sq = (diff_x)**2 + (diff_y)**2
    min_d = min(dist_sq)
    temp=np.argwhere(dist_sq==min_d)
    target_pt = int(temp[0,0]) + point
    return target_pt  

################################################################################################### destination_check
def destination_check(state, goal, target_pt, length_path):
    a=0
    dist_to_dest = (state.x-goal[0])**2+(state.y-goal[1])**2
    if dist_to_dest < accept_dist:
        a += 1
    if state.v < abs(accept_stop_v):
        a += 1
    if abs(target_pt - length_path) < 5:
        a += 1
    if a==3:
        return True
    return False

################################################################################################### run_controller
def run_controller(path_x, path_y, path_yaw,  \
                    dist_step, initial_state, goal,\
                    ox, oy, velX, velY, path_planning):
    current_state = initial_state
    imgct=0
    #Initialize variables to store actual state values of car
    x = [current_state.x]
    y = [current_state.y]
    yaw = [current_state.yaw]
    vel = [current_state.v]
    t = [0]
    steer = [0]
    acc = [0]
    lyap=[0]
    lu=[0]
    lx=[0]
    ldu=[0]

    mpc_acc = np.zeros(H)
    mpc_steer = np.zeros(H)
    cur_state_vec=current_state.state_to_vec()
    target_pt = get_closest_point_on_path(path_x, path_y, cur_state_vec, 0)
    while t[-1] <= simulation_time_limit:
        imgct +=1
        cur_state_vec = current_state.state_to_vec()
        
        traj_des, target_pt, steer_des = cal_desired_trajectory(cur_state_vec, path_x, path_y,dist_step, path_yaw,target_pt)
        
        mpc_x, mpc_y, mpc_yaw, mpc_v, mpc_acc, mpc_steer, lyap_val, lap_u, lap_x, lap_du = run_MPC(traj_des, cur_state_vec, mpc_acc, mpc_steer, steer_des, goal)  


        current_state.update_state(mpc_acc[0], mpc_steer[0])
        
        time = t[-1] + dt
        t.append(time)
        x.append(current_state.x)
        y.append(current_state.y)
        yaw.append(current_state.yaw)
        vel.append(current_state.v)
        steer.append(mpc_steer[0])
        acc.append(mpc_acc[0])
        lyap.append(lyap_val)
        lu.append(lap_u)
        lx.append(lap_x)
        ldu.append(lap_du)

        if destination_check(current_state, goal, target_pt, len(path_x)):
            print("Reached destination")
            break

        ox=np.add(ox,velX)
        oy=np.add(oy,velY)

        plt.cla()
        plt.plot(mpc_x, mpc_y, "xr", label="MPC")
        plt.plot(path_x, path_y, "-r", label="course")
        plt.plot(ox,oy,'ok')
        plt.plot(x, y, "ob", label="trajectory")
        if run_code==1:
            plt.plot(gx,gy,'om')
        plt.plot(traj_des[0, :], traj_des[1, :], "xk", label="xref")
        plt.plot(path_x[target_pt], path_y[target_pt], "xg", label="target")
        plot_car(current_state.x, current_state.y, current_state.yaw, mpc_steer[0])
        plt.axis("equal")
        plt.grid(True)
        plt.title("Time[s]:" + str(round(time, 2))
                    + ", speed[m/s]:" + str(round(current_state.v , 2)))
        if save_simulation:
            plt.savefig('Q_'+str(imgct))
        plt.pause(0.0001)

        if path_planning:
            path_x,path_y,path_yaw, ox, oy = pot_field_path(current_state.x, current_state.y, \
                                                             ox, oy, velX, velY, dist_step)
            #gx+=1
            #gy+=1
            if stop_planning(path_x,path_y):
                path_planning = False

    return t, x, y, yaw, vel, steer, acc, lyap, lu, lx, ldu
    #end

def stop_planning(path_x,path_y):
    dist_to_dest = (path_x[-1]-gx)**2+(path_y[-1]-gy)**2
    if dist_to_dest < accept_dist:
        return True
    else:
        return False
################################################################################################### get_spline_path
def get_right_turn(dl):
    ax = [0.0, 10.0, 15.0, 20.0, 20.0, 20.0, 20.0]
    ay = [0.0, 1.0, 0.0, 0.0, 5.0, 10.0, 20.0]
    cx, cy, cyaw, ck, s = cubic_spline_planner.calc_spline_course(
        ax, ay, ds=dl)

    return cx, cy, cyaw


def get_forward_course(dl):
    ax = np.array([0.0, 10.0, 20.0, 25.0, 30.0, 40.0])
    ay = np.array([0.0, 5.0, 0.0, 0.0, 0.0, 0.0])
    cx, cy, cyaw, ck, s = cubic_spline_planner.calc_spline_course(
        ax, ay, ds=dl)

    return cx, cy, cyaw

def get_straight_course(dl):
    ax = [0.0, 18.0]
    ay = [0.0, 0.0]
    cx, cy, cyaw, ck, s = cubic_spline_planner.calc_spline_course(
        ax, ay, ds=dl)

    return cx, cy, cyaw

########################################################################################################################################### 
#                                                                                                                                         #
#                                                                                                                                         #
#                       PATH PLANNING                                                                                                     #  
#                                                                                                                                         #                                        
#                                                                                                                                         #
###########################################################################################################################################  
# Parameters
KP = 15.0  # attractive potential gain
ETA = 500.0  # repulsive potential gain

show_animation=True

def calc_attractive_potential(x, y, gx, gy):
    return 0.5 * KP * np.hypot(x - gx, y - gy) #+ 0.5*10*np.hypot(y-0,0)


def calc_repulsive_potential(x, y, ox, oy, obs):
    obs =   len(ox)
    pot=0
    for i in range(obs):
        pot += 0.5*ETA*np.exp(-np.hypot(x-ox[i],y-oy[i]))
    return  pot

def get_motion_model():
    motion = []
    num=50
    for i in range(num*2):
        deg=2*i*np.pi/num
        motion.append([np.cos(deg),np.sin(deg)])
    
   

    return motion


def potential_field_planning(sx, sy, gx, gy, ox, oy, reso, rr,obs):
     mot=get_motion_model()
     predictX=[]
     predictY=[]
     for i in range(len(mot)):
            predictX.append(sx + mot[i][0]*reso)
            predictY.append(sy + mot[i][1]*reso)
     
     gnet=[]
     min_gnet=0
     min_gnet_pos=0
     for i in range(len(mot)):
            ga = calc_attractive_potential(predictX[i],predictY[i],gx,gy)
            gr = calc_repulsive_potential(predictX[i],predictY[i],ox,oy,obs)
            gnet.append(ga + gr)
         
            
            if(i==0):
                min_gnet=ga+gr
                min_gnet_pos=i
            else:
                if(min_gnet>ga+gr):
                     min_gnet=ga+gr
                     min_gnet_pos=i 
     
  
     step_x = mot[min_gnet_pos][0]
     step_y = mot[min_gnet_pos][1]
        
     return [step_x,step_y]

def initialize_obstacles(NUM_OF_OBSTACLES):
        
    if road:
        ox=[20,40,50,65,80,95,110]
        oy=[-2,2,-2,2,-2,2,-2]
        velX=[0.04,0.04,0.04,0.04,0.04,0.04,0.04]
        velY=[0,0,0,0,0,0,0]
    else:
        coordinateX=[]
        coordinateY=[]
        velX =[]
        velY =[]
    
        for i in range(1,NUM_OF_OBSTACLES):
             coordinateX.append(random.randrange(10, gx, 1))
             coordinateY.append(random.randrange(10, gy, 1))
             velX.append((np.random.random()/40)*(-1)**i)
             velY.append((np.random.random()/40)*(-1)**i)
        
        ox = coordinateX  
        oy = coordinateY 
    return ox,oy,velX,velY

def get_spline_path(ax,ay,dl):
    cx, cy, cyaw, ck, s = cubic_spline_planner.calc_spline_course(
        ax, ay, ds=dl)

    return cx, cy, cyaw

def pot_field_path(cx, cy, ox, oy, velX, velY, dl):
    iter = 0
    pathX=np.array([])
    pathY=np.array([])
    while iter<=H+5:
         [step_x,step_y] = potential_field_planning(
         cx, cy, gx, gy, ox, oy, grid_size, robot_radius,NUM_OF_OBSTACLES)
         cx=cx+step_x
         cy=cy+step_y

         ox=np.add(ox,velX)
         oy=np.add(oy,velY)

         pathX=np.append(pathX, cx)
         pathY=np.append(pathY, cy)
         iter += 1
    pathX, pathY, pathYaw = get_spline_path(pathX,pathY,dl)
    return pathX, pathY, pathYaw, ox, oy

################################################################################################### main_only_mpc
def main_only_mpc():
    dist_step=1
    path_planning = False
    #path_x,path_y,path_yaw = get_right_turn(dist_step)
    path_x,path_y,path_yaw = get_forward_course(dist_step)
    #path_x,path_y,path_yaw = get_straight_course(dist_step)
    ox,oy,velX,velY = initialize_obstacles(0)
    
    initial_state= State(sx, sy, path_yaw[0], 0.0)

    goal = np.array([path_x[-1], path_y[-1]])

    t, x, y, yaw, vel, steer, acc, lyap, lu, lx, ldu = run_controller(path_x, path_y, path_yaw, \
                                                    dist_step, initial_state, goal, \
                                                    ox, oy, velX, velY, path_planning)
    plt.close("all")
    plt.subplots()
    plt.plot(path_x, path_y, "-r", label="spline")
    plt.plot(x, y, "--g", label="tracking")
    plt.grid(True)
    plt.axis("equal")
    plt.xlabel("x[m]")
    plt.ylabel("y[m]")
    plt.legend()

    plt.subplots()
    plt.plot(t, vel, "-r", label="speed")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Speed [m/s]")

    plt.subplots()
    plt.plot(t, lyap, "-r", label="Lyaunov")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Lyaunov")
    plt.show()

    plt.subplots()
    plt.plot(t, steer, "-r", label="Steering angles")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Steering angles")
    plt.show()

    plt.subplots()
    plt.plot(t, acc, "-r", label="Acceleration")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Acceleration [m/s^2]")
    plt.show()

    
################################################################################################### main_only_path
def main_only_path():
    print("potential_field_planning start")



    coordinateX=[]
    coordinateY=[]
    velX =[]
    velY =[]
    
    for i in range(1,NUM_OF_OBSTACLES):
         coordinateX.append(random.randrange(0, 50, 1))
         coordinateY.append(random.randrange(0,50,1))
         velX.append(np.random.random()/5)
         velY.append(np.random.random()/5)
        
    ox = coordinateX  
    oy = coordinateY 
   
         
    cx =sx
    cy=sy
    
    if show_animation:
          plt.grid(True)
          plt.axis("equal")
          plt.plot(ox,oy,'x')
          plt.plot(gx,gy,'r.')

    iter = 0
    pathX=[]
    pathY=[]
    while iter<=100:
         [step_x,step_y] = potential_field_planning(
         cx, cy, gx, gy, ox, oy, grid_size, robot_radius,NUM_OF_OBSTACLES)
         cx=cx+step_x
         cy=cy+step_y

         ox=np.add(ox,velX)
         oy=np.add(oy,velY)

         pathX.append(cx)
         pathY.append(cy)
         iter += 1
 
         if show_animation:
                plt.clf()
                plt.plot(cx, cy, ".r")
                plt.plot(ox,oy,'x')
                plt.plot(ox,oy,'x')
                plt.plot(gx,gy,'r.')
                plt.plot(pathX,pathY,'.r')
                plt.pause( 0.01)
               
   
    if show_animation:
        plt.show()
   
################################################################################################### main

def main():
    
    dist_step=1
    cx = sx
    cy = sy
    ox,oy,velX,velY = initialize_obstacles(NUM_OF_OBSTACLES)
    
    path_x,path_y,path_yaw, ox, oy = pot_field_path(cx, cy, ox, oy, velX, velY, dist_step)

    #path_x,path_y,path_yaw = get_right_turn(dist_step)
    #path_x,path_y,path_yaw = get_forward_course(dist_step)
    #path_x,path_y,path_yaw = get_straight_course(dist_step)

    initial_state= State(path_x[0], path_y[0], path_yaw[0], 0.0)

    goal = np.array([gx, gy])

    t, x, y, yaw, vel, steer, acc, lyap, lu, lx, ldu = run_controller(path_x, path_y, path_yaw, \
                                                    dist_step, initial_state, goal, \
                                                    ox, oy, velX, velY, path_planning)

   # plt.close("all")
  

    plt.subplots()
    plt.plot(t, vel, "-r", label="speed")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Speed [kmh]")
    
    plt.subplots()
    plt.plot(t, acc, "-r", label="Acceleration")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Acceleration [m/s^2]")
    plt.show()


if __name__ == '__main__':
    if run_code==1:
        main()
    if run_code==2:
        main_only_mpc()
    if run_code==3:
        main_only_path()