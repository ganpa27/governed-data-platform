from PIL import Image, ImageDraw, ImageFont
import os

width, height = 1200, 800
img = Image.new('RGB', (width, height), 'white')
d = ImageDraw.Draw(img)
font = ImageFont.load_default()

coords = [
    (50,50,350,150,'End Users & Identity'),
    (50,200,350,300,'API Gateway & Router'),
    (400,50,700,150,'Path A: Predefined'),
    (400,200,700,300,'Path B: AI-powered'),
    (800,125,1100,225,'Database'),
    (800,300,1100,400,'Governance'),
]
for x1,y1,x2,y2,text in coords:
    d.rectangle([x1,y1,x2,y2], outline='black', width=2)
    d.text((x1+5,y1+5), text, fill='black', font=font)

# arrows
nd = d
d.line([(200,150),(200,200)], fill='black', width=2)
d.polygon([(195,195),(205,195),(200,205)], fill='black')

d.line([(350,250),(400,250)], fill='black', width=2)
d.polygon([(395,245),(405,245),(400,255)], fill='black')

d.line([(350,100),(400,100)], fill='black', width=2)
d.polygon([(395,95),(405,95),(400,105)], fill='black')

nd.line([(700,100),(800,100)], fill='black', width=2)
d.polygon([(795,95),(805,95),(800,105)], fill='black')

nd.line([(700,250),(800,250)], fill='black', width=2)
d.polygon([(795,245),(805,245),(800,255)], fill='black')

nd.line([(950,225),(950,300)], fill='black', width=2)
d.polygon([(945,295),(955,295),(950,305)], fill='black')

output_path = os.path.join('Architecture_Diagrams','governed_platform_architecture_v2.png')
img.save(output_path)
print('saved to', output_path)
