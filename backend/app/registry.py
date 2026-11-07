"""Configurable engineering demonstration ranges, not approved specifications."""
PROCESSES = {
 'fermentation': [('temperature',36,38,'°C'),('pH',6.8,7.4,'pH'),('dissolved_oxygen',30,70,'%'),('agitation',150,350,'rpm'),('airflow',1,3,'L/min'),('feed_rate',2,6,'mL/min'),('pressure',0.8,1.2,'bar'),('biomass',5,15,'g/L'),('glucose',2,8,'g/L'),('lactate',0.2,2,'g/L'),('titer',1,5,'g/L')],
 'tablet': [('moisture',2,4,'%'),('granulation_temperature',25,35,'°C'),('impeller_speed',100,200,'rpm'),('chopper_speed',1000,1500,'rpm'),('drying_temperature',50,65,'°C'),('drying_time',30,50,'min'),('blend_uniformity',95,105,'%'),('compression_force',10,20,'kN'),('tablet_weight',490,510,'mg'),('hardness',6,10,'kp'),('disintegration_time',3,12,'min')],
 'sterile': [('temperature',18,22,'°C'),('humidity',40,60,'%'),('differential_pressure',10,20,'Pa'),('particle_count',0,3520,'particles/m³'),('environmental_monitoring',0,1,'CFU'),('equipment_status',0.9,1.1,'state'),('duration',10,60,'min'),('utility_conductivity',0.1,1.3,'µS/cm')],
 'liquid': [('mixing_speed',100,200,'rpm'),('mixing_time',15,30,'min'),('temperature',20,30,'°C'),('pH',5.5,7,'pH'),('viscosity',80,120,'cP'),('conductivity',1,3,'mS/cm'),('volume',990,1010,'L'),('filling_weight',98,102,'g'),('filling_speed',60,100,'units/min')]
}

def definitions():
 return [{'id': k, 'name': k.title(), 'parameters': [{'name':n,'low':l,'high':h,'unit':u} for n,l,h,u in v], 'synthetic':True} for k,v in PROCESSES.items()]
